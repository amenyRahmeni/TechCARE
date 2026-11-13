import base64
from datetime import timedelta
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
import uuid

from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
import requests

from .models import Notification, PushDelivery, PushSubscription
from .services import reminder_key


def configured():
    return bool(settings.WEBPUSH_PUBLIC_KEY and Path(settings.WEBPUSH_PRIVATE_KEY).is_file())


def validate_subscription(data):
    if not isinstance(data, dict):
        raise ValidationError("Abonnement navigateur invalide.")
    endpoint = data.get("endpoint", "")
    if not isinstance(endpoint, str) or not 20 <= len(endpoint) <= 2048:
        raise ValidationError("Adresse du service de notifications invalide.")
    try:
        parsed = urlsplit(endpoint)
        host = (parsed.hostname or "").lower()
        allowed = host in {"fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com"} or host.endswith(".notify.windows.com")
        valid = allowed and parsed.scheme == "https" and parsed.port in (None, 443) and not parsed.username and not parsed.password and not parsed.fragment and parsed.path not in ("", "/")
    except ValueError:
        valid = False
    if not valid:
        raise ValidationError("Ce service de notifications n’est pas pris en charge.")
    keys = data.get("keys")
    if not isinstance(keys, dict):
        raise ValidationError("Les clés de l’abonnement sont manquantes.")
    try:
        raw = {}
        for key, length in (("p256dh", 65), ("auth", 16)):
            value = keys[key]
            if not isinstance(value, str) or not 10 <= len(value) <= 100:
                raise ValueError
            raw[key] = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
            if len(raw[key]) != length:
                raise ValueError
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw["p256dh"])
    except (KeyError, ValueError, TypeError):
        raise ValidationError("Les clés de l’abonnement sont invalides.") from None
    return {"endpoint": endpoint, "endpoint_hash": hashlib.sha256(endpoint.encode()).hexdigest(), "p256dh": keys["p256dh"], "auth": keys["auth"]}


class NoRedirectSession(requests.Session):
    def request(self, method, url, **kwargs):
        kwargs["allow_redirects"] = False
        return super().request(method, url, **kwargs)


def notification_current(item):
    if item.expires_at and item.expires_at <= timezone.now():
        return False
    if item.kind == Notification.Kind.REMINDER:
        return bool(item.appointment_id and item.appointment.status == "confirmed" and item.event_key == reminder_key(item.appointment))
    if item.kind == Notification.Kind.RECOMMENDATION:
        from appointments.permissions import can_use_client_features
        return bool(item.recommendation_id and item.recommendation.is_active and item.recommendation.rule.is_active and item.recommendation.pc.owner_id == item.recipient_id and can_use_client_features(item.recipient))
    return True


def relevant(delivery):
    item, sub = delivery.notification, delivery.subscription
    return sub.is_active and sub.user.is_active and sub.user_id == item.recipient_id and notification_current(item)


def dispatch_push(limit=30):
    """Claim an outbox batch, then send outside transactions with bounded retries."""
    if not configured():
        return {"sent": 0, "failed": 0, "cancelled": 0}
    from pywebpush import WebPushException, webpush
    now = timezone.now()
    expired = PushDelivery.objects.filter(state="processing", locked_at__lt=now - timedelta(minutes=5))
    expired.filter(attempts__gte=5).update(state="failed", locked_at=None, lease=None, last_error="Traitement interrompu")
    expired.filter(attempts__lt=5).update(state="pending", locked_at=None, lease=None)
    lease = uuid.uuid4()
    with transaction.atomic():
        ids = list(PushDelivery.objects.select_for_update(skip_locked=True).filter(state="pending", next_attempt_at__lte=now).order_by("pk").values_list("pk", flat=True)[:limit])
        PushDelivery.objects.filter(pk__in=ids).update(state="processing", locked_at=now, lease=lease, attempts=F("attempts") + 1)
    results = {"sent": 0, "failed": 0, "cancelled": 0}
    deliveries = PushDelivery.objects.filter(pk__in=ids, lease=lease).select_related("subscription__user", "notification__appointment", "notification__recommendation__rule", "notification__recommendation__pc")
    for delivery in deliveries:
        selected = PushDelivery.objects.filter(pk=delivery.pk, lease=lease, state="processing")
        if not relevant(delivery):
            selected.update(state="cancelled", locked_at=None, lease=None)
            results["cancelled"] += 1
            continue
        try:
            sub = delivery.subscription
            validate_subscription({"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}})
            item = delivery.notification
            payload = json.dumps({"id": item.pk, "recipient_id": item.recipient_id, "title": item.title, "body": item.message, "url": f"/notifications/?notification={item.pk}"}, ensure_ascii=False)
            with NoRedirectSession() as session:
                ttl = max(0, min(86400, int((item.expires_at - timezone.now()).total_seconds()))) if item.expires_at else 86400
                response = webpush(subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}, data=payload, vapid_private_key=settings.WEBPUSH_PRIVATE_KEY, vapid_claims={"sub": settings.WEBPUSH_SUBJECT}, ttl=ttl, timeout=10, requests_session=session)
            if not 200 <= response.status_code < 300:
                raise WebPushException("Envoi refusé", response=response)
        except (WebPushException, requests.RequestException, ValidationError, ValueError, OSError) as error:
            response = getattr(error, "response", None)
            code = getattr(response, "status_code", None)
            if code in (404, 410):
                PushSubscription.objects.filter(pk=delivery.subscription_id).update(is_active=False)
            retry = (code is None or code in (408, 429) or code >= 500) and delivery.attempts < 5 and not isinstance(error, ValidationError)
            selected.update(state="pending" if retry else "failed", locked_at=None, lease=None, next_attempt_at=timezone.now() + timedelta(seconds=min(3600, 30 * 2 ** delivery.attempts)), last_error=f"HTTP {code}" if code else type(error).__name__)
            results["failed"] += 1
        else:
            selected.update(state="sent", sent_at=timezone.now(), locked_at=None, lease=None, last_error="")
            results["sent"] += 1
    return results
