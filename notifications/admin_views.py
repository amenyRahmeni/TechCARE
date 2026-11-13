from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from backoffice.views import staff_required

from .campaigns import recipients, send_campaign, withdraw_campaign
from .forms import CampaignForm
from .models import Notification, NotificationCampaign, PushDelivery


def campaign_list():
    return NotificationCampaign.objects.select_related("author", "withdrawn_by").annotate(read_count=Count("notifications", filter=Q(notifications__read_at__isnull=False)), available_count=Count("notifications")).order_by("-sent_at", "-pk")


@staff_required
@require_GET
def overview(request):
    campaigns = campaign_list()
    stats = campaigns.aggregate(total=Count("pk"), recipients=Sum("recipient_count"), withdrawn=Count("pk", filter=Q(withdrawn_at__isnull=False)))
    stats["read"] = Notification.objects.filter(campaign__isnull=False, read_at__isnull=False).count()
    q = request.GET.get("q", "").strip()[:100]
    audience, state = request.GET.get("audience", ""), request.GET.get("state", "")
    if q:
        campaigns = campaigns.filter(Q(title__icontains=q) | Q(message__icontains=q))
    if audience in NotificationCampaign.Audience.values:
        campaigns = campaigns.filter(audience=audience)
    if state in {"sent", "withdrawn"}:
        campaigns = campaigns.filter(withdrawn_at__isnull=state == "sent")
    automatic = Notification.objects.current().filter(campaign__isnull=True, repair__isnull=True)
    automatic_counts = automatic.aggregate(
        reminders=Count("pk", filter=Q(kind="reminder")),
        appointments=Count("pk", filter=Q(kind__in=["booking", "assignment", "confirmed", "updated", "cancelled"])),
        maintenance=Count("pk", filter=Q(kind="recommendation")),
        updates=Count("pk", filter=Q(kind__in=["status", "documents", "component"])),
    )
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "notifications/manage.html", {"active_page": "notification_management", "page_obj": Paginator(campaigns, 10).get_page(request.GET.get("page")), "page_query": params.urlencode(), "stats": stats, "automatic": automatic_counts, "q": q, "audience": audience, "state": state, "audiences": NotificationCampaign.Audience.choices})


@staff_required
@require_http_methods(["GET", "POST"])
def compose(request):
    form = CampaignForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            campaign, created = send_campaign(request.user, token=data["token"], audience=data["audience"], title=data["title"], message=data["message"], level=data["level"], selected=data["recipients"].values_list("pk", flat=True))
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, f"Notification envoyée à {campaign.recipient_count} destinataire(s)." if created else "Cet envoi a déjà été enregistré ; aucun doublon n’a été créé.")
            return redirect(campaign)
    counts = {key: recipients(key).count() for key in ["all", "clients", "technicians"]}
    return render(request, "notifications/compose.html", {"active_page": "notification_management", "form": form, "audience_counts": counts})


@staff_required
@require_GET
def detail(request, pk):
    campaign = get_object_or_404(campaign_list(), pk=pk)
    items = campaign.notifications.select_related("recipient", "recipient__technician_profile").annotate(
        push_sent=Count("push_deliveries", filter=Q(push_deliveries__state="sent")),
        push_pending=Count("push_deliveries", filter=Q(push_deliveries__state__in=["pending", "processing"])),
        push_failed=Count("push_deliveries", filter=Q(push_deliveries__state="failed")),
    ).order_by("recipient__first_name", "recipient__last_name", "pk")
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()[:100]
    if status in {"read", "unread"}:
        items = items.filter(read_at__isnull=status == "unread")
    if q:
        items = items.filter(Q(recipient__first_name__icontains=q) | Q(recipient__last_name__icontains=q) | Q(recipient__email__icontains=q) | Q(recipient__username__icontains=q))
    push = PushDelivery.objects.filter(notification__campaign=campaign).aggregate(sent=Count("pk", filter=Q(state="sent")), pending=Count("pk", filter=Q(state__in=["pending", "processing"])), failed=Count("pk", filter=Q(state="failed")))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "notifications/campaign_detail.html", {"active_page": "notification_management", "campaign": campaign, "page_obj": Paginator(items, 12).get_page(request.GET.get("page")), "page_query": params.urlencode(), "push": push, "q": q, "status": status})


@staff_required
@require_POST
def withdraw(request, pk):
    try:
        campaign = withdraw_campaign(request.user, pk)
    except NotificationCampaign.DoesNotExist:
        raise Http404 from None
    messages.success(request, "Notification retirée des centres des destinataires. L’historique est conservé.")
    return redirect(campaign)
