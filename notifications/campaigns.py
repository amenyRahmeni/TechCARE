"""Administrator announcements; business event notifications stay independent."""
import hashlib
import json
import uuid

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Notification, NotificationCampaign, PushDelivery
from .services import notify


def recipients(audience="all", selected=()):
    users = get_user_model().objects.filter(is_active=True, is_staff=False, is_superuser=False)
    if audience == NotificationCampaign.Audience.CLIENTS:
        users = users.filter(technician_profile__isnull=True)
    elif audience == NotificationCampaign.Audience.TECHNICIANS:
        users = users.filter(technician_profile__isnull=False)
    elif audience == NotificationCampaign.Audience.SELECTED:
        users = users.filter(pk__in=selected)
    elif audience != NotificationCampaign.Audience.ALL:
        return users.none()
    return users.order_by("pk")


def require_admin(actor):
    if not actor.is_authenticated or not actor.is_active or not actor.is_staff:
        raise PermissionDenied("Cet espace est réservé aux administrateurs.")


@transaction.atomic
def send_campaign(actor, *, token, audience, title, message, level, selected=()):
    require_admin(actor)
    try:
        token = uuid.UUID(str(token))
        selected = sorted({int(pk) for pk in selected}) if audience == "selected" else []
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("La demande d’envoi est invalide. Rechargez le formulaire.") from None
    title, message = title.strip(), message.strip()
    if audience not in NotificationCampaign.Audience.values or level not in Notification.Level.values or not title or not message or len(title) > 150 or len(message) > 700:
        raise ValidationError("Vérifiez le public, la priorité, le titre et le message.")
    fingerprint = hashlib.sha256(json.dumps([audience, selected, title, message, level], ensure_ascii=False).encode()).hexdigest()
    # Serialise submissions from this author, including double clicks and retries.
    current_actor = get_user_model().objects.select_for_update().get(pk=actor.pk)
    require_admin(current_actor)
    existing = NotificationCampaign.objects.filter(token=token).first()
    if existing:
        if existing.author_id != actor.pk or existing.payload_hash != fingerprint:
            raise ValidationError("Ce formulaire a déjà servi à un autre envoi. Ouvrez une nouvelle notification.")
        return existing, False
    targets = list(recipients(audience, selected).select_for_update())
    if not targets:
        raise ValidationError("Aucun compte actif ne correspond à ce public.")
    if audience == "selected" and {user.pk for user in targets} != set(selected):
        raise ValidationError("Un destinataire n’est plus disponible. Vérifiez votre sélection.")
    campaign = NotificationCampaign.objects.create(token=token, author=actor, audience=audience, title=title, message=message, level=level, payload_hash=fingerprint, recipient_count=len(targets))
    for target in targets:
        notify(target.pk, kind=Notification.Kind.ANNOUNCEMENT, title=title, message=message, level=level, event_key=f"campaign:{campaign.pk}", campaign=campaign)
    LogEntry.objects.log_actions(user_id=actor.pk, queryset=[campaign], action_flag=ADDITION, change_message=f"Notification envoyée à {len(targets)} compte(s).", single_object=True)
    return campaign, True


@transaction.atomic
def withdraw_campaign(actor, pk):
    require_admin(actor)
    campaign = NotificationCampaign.objects.select_for_update().get(pk=pk)
    if campaign.withdrawn_at:
        return campaign
    campaign.withdrawn_at = timezone.now()
    campaign.withdrawn_by = actor
    campaign.save(update_fields=["withdrawn_at", "withdrawn_by"])
    campaign.notifications.update(expires_at=campaign.withdrawn_at)
    PushDelivery.objects.filter(notification__campaign=campaign, state__in=["pending", "processing", "failed"]).update(state="cancelled", locked_at=None, lease=None)
    LogEntry.objects.log_actions(user_id=actor.pk, queryset=[campaign], action_flag=CHANGE, change_message="Notification retirée des centres des destinataires ; historique conservé.", single_object=True)
    return campaign
