import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .models import Notification, PushDelivery, PushSubscription
from .push import configured, notification_current, validate_subscription
from .signals import COOKIE_NAME, COOKIE_SALT, device_token

GROUPS = {
    "appointments": ["booking", "assignment", "confirmed", "updated", "cancelled", "reminder"],
    "interventions": ["status", "documents", "component", "message"],
    "maintenance": ["recommendation"],
    "administration": ["announcement"],
}


def owned(request):
    return Notification.objects.current().filter(recipient=request.user)


@never_cache
@login_required
@require_GET
def inbox(request):
    items = owned(request)
    counts = items.aggregate(total=Count("pk"), unread=Count("pk", filter=Q(read_at__isnull=True)), warning=Count("pk", filter=Q(level="warning")), latest=Max("pk"))
    status = request.GET.get("status", "")
    group = request.GET.get("group", "")
    q = request.GET.get("q", "").strip()[:100]
    if status == "unread":
        items = items.filter(read_at__isnull=True)
    if group in GROUPS:
        items = items.filter(kind__in=GROUPS[group])
    if q:
        items = items.filter(Q(title__icontains=q) | Q(message__icontains=q))
    params = request.GET.copy()
    params.pop("page", None)
    token = device_token(request)
    enabled = bool(token and PushSubscription.objects.filter(user=request.user, browser_token=token, is_active=True).exists())
    return render(request, "notifications/inbox.html", {"active_page": "notifications", "workspace_base": "backoffice/base.html" if request.user.is_staff else "base.html", "page_obj": Paginator(items, 12).get_page(request.GET.get("page")), "counts": counts, "status": status, "group": group, "q": q, "page_query": params.urlencode(), "push_configured": configured(), "push_public_key": settings.WEBPUSH_PUBLIC_KEY, "push_enabled": enabled, "highlight": request.GET.get("notification", "")[:20]})


@never_cache
@login_required
@require_GET
def feed(request):
    try:
        raw = request.GET.get("since", "0")
        if len(raw) > 20:
            raise ValueError
        since = int(raw)
        if not 0 <= since <= 2 ** 63 - 1:
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse({"error": "Repère de notification invalide."}, status=400)
    items = owned(request)
    stats = items.aggregate(unread=Count("pk", filter=Q(read_at__isnull=True)), latest=Max("pk"))
    latest = stats["latest"] or 0
    # Deliver oldest unseen first so a burst larger than 20 cannot skip alerts.
    fresh = list(items.filter(pk__gt=since).order_by("pk")[:20])
    cursor = fresh[-1].pk if fresh else max(since, latest)
    return JsonResponse({"unread": stats["unread"], "latest": cursor, "items": [{"id": item.pk, "title": item.title, "message": item.message, "level": item.level, "url": f"/notifications/?notification={item.pk}"} for item in fresh]})


@login_required
@require_POST
def read(request, pk, value=True):
    item = get_object_or_404(owned(request), pk=pk)
    Notification.objects.filter(pk=item.pk, recipient=request.user).update(read_at=timezone.now() if value else None)
    return redirect("notifications:list")


@login_required
@require_POST
def read_all(request):
    try:
        through = int(request.POST.get("through", "0"))
    except ValueError:
        through = 0
    owned(request).filter(pk__lte=through, read_at__isnull=True).update(read_at=timezone.now())
    messages.success(request, "Les notifications affichées ont été marquées comme lues.")
    return redirect("notifications:list")


@login_required
@require_POST
def visit(request, pk):
    item = get_object_or_404(owned(request).select_related("appointment__technician", "recommendation__pc"), pk=pk)
    Notification.objects.filter(pk=item.pk, recipient=request.user).update(read_at=timezone.now())
    return redirect(item.target_url(request.user))


@never_cache
@login_required
@require_POST
def subscribe(request):
    if not configured():
        return JsonResponse({"error": "Les notifications navigateur sont temporairement indisponibles."}, status=503)
    if len(request.body) > 4096:
        return JsonResponse({"error": "Abonnement trop volumineux."}, status=400)
    try:
        data = validate_subscription(json.loads(request.body))
    except (ValueError, ValidationError) as error:
        return JsonResponse({"error": " ".join(error.messages) if isinstance(error, ValidationError) else "Abonnement invalide."}, status=400)
    token = device_token(request)
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        sub = PushSubscription.objects.select_for_update().filter(endpoint_hash=data["endpoint_hash"]).first()
        if sub and (sub.endpoint != data["endpoint"] or (sub.user_id != request.user.pk and sub.browser_token != token)):
            return JsonResponse({"error": "Réactivez l’abonnement de ce navigateur pour ce compte.", "renew": True}, status=409)
        if not sub and PushSubscription.objects.filter(user=request.user).count() >= 20:
            return JsonResponse({"error": "La limite de navigateurs enregistrés est atteinte."}, status=400)
        if sub:
            if sub.user_id != request.user.pk:
                PushDelivery.objects.filter(subscription=sub, state="pending").update(state="cancelled")
            sub.user = request.user
            sub.p256dh, sub.auth = data["p256dh"], data["auth"]
            sub.is_active = True
            sub.save()
        else:
            sub = PushSubscription.objects.create(user=request.user, **data)
    response = JsonResponse({"enabled": True})
    response.set_signed_cookie(COOKIE_NAME, str(sub.browser_token), salt=COOKIE_SALT, max_age=365 * 86400, httponly=True, samesite="Lax", secure=request.is_secure())
    return response


@never_cache
@login_required
@require_POST
def unsubscribe(request):
    token = device_token(request)
    if token:
        with transaction.atomic():
            subscriptions = PushSubscription.objects.filter(user=request.user, browser_token=token)
            PushDelivery.objects.filter(subscription__in=subscriptions, state="pending").update(state="cancelled")
            subscriptions.update(is_active=False)
    return JsonResponse({"enabled": False})


@never_cache
@require_GET
def push_session(request):
    if not request.user.is_authenticated:
        return JsonResponse({"active": False}, status=401)
    token = device_token(request)
    active = bool(token and PushSubscription.objects.filter(user=request.user, browser_token=token, is_active=True).exists())
    if active and "notification" in request.GET:
        raw = request.GET.get("notification", "")
        item = None
        if raw.isdecimal() and len(raw) <= 18:
            item = owned(request).filter(pk=int(raw)).select_related("appointment", "recommendation__rule", "recommendation__pc").first()
        active = bool(item and notification_current(item))
    return JsonResponse({"active": active, "user_id": request.user.pk})


@never_cache
@require_GET
def service_worker(request):
    response = FileResponse((settings.BASE_DIR / "static/js/notifications-sw.js").open("rb"), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["X-Content-Type-Options"] = "nosniff"
    return response
