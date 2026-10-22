from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Case, Count, Exists, IntegerField, OuterRef, Q, Value, When
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import PCForm
from .models import MaintenanceRecord, PC, Recommendation
from .services import refresh_all_recommendations


def owned_pcs(user):
    return PC.objects.filter(owner=user)


def active_recommendations(user):
    return Recommendation.objects.filter(pc__owner=user, is_active=True, rule__is_active=True).select_related("pc", "rule").annotate(
        priority_rank=Case(When(rule__priority="high", then=Value(0)), When(rule__priority="medium", then=Value(1)), default=Value(2), output_field=IntegerField())
    ).order_by("priority_rank", "rule__pk", "pc__name")


def decorate_pcs(queryset):
    active = Recommendation.objects.filter(pc=OuterRef("pk"), is_active=True, rule__is_active=True)
    return queryset.annotate(needs_attention=Exists(active)).annotate(
        active_recommendation_count=Count("recommendations", filter=Q(recommendations__is_active=True, recommendations__rule__is_active=True), distinct=True)
    ).prefetch_related("maintenance_records")


@login_required
def pc_list(request):
    all_pcs = decorate_pcs(owned_pcs(request.user))
    recs = active_recommendations(request.user)
    total = all_pcs.count()
    attention = all_pcs.filter(needs_attention=True).count()
    q = request.GET.get("q", "").strip()[:100]
    device_type = request.GET.get("type", "")
    status = request.GET.get("status", "")
    sort = request.GET.get("sort", "recent")
    pcs = all_pcs
    if q:
        pcs = pcs.filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(model__icontains=q) | Q(serial_number__icontains=q))
    if device_type in PC.DeviceType.values:
        pcs = pcs.filter(device_type=device_type)
    if status in ("attention", "healthy"):
        pcs = pcs.filter(needs_attention=(status == "attention"))
    pcs = pcs.order_by({"recent": "-created_at", "name": "name", "oldest": "created_at"}.get(sort, "-created_at"), "pk")
    page = Paginator(pcs, 8).get_page(request.GET.get("page"))
    page_query = request.GET.copy()
    page_query.pop("page", None)
    return render(request, "maintenance/pc_list.html", {
        "active_page": "pcs", "page_obj": page, "total": total, "attention": attention,
        "healthy": total - attention, "recommendation_count": recs.count(),
        "q": q, "device_type": device_type, "status": status, "sort": sort,
        "filtered": bool(q or device_type or status), "page_query": page_query.urlencode(),
        "featured_recommendations": recs[:2],
    })


@login_required
def pc_detail(request, pk):
    pc = get_object_or_404(decorate_pcs(owned_pcs(request.user)), pk=pk)
    return render(request, "maintenance/pc_detail.html", {"active_page": "pcs", "pc": pc, "recommendations": active_recommendations(request.user).filter(pc=pc)})


@login_required
def pc_form(request, pk=None):
    pc = get_object_or_404(owned_pcs(request.user), pk=pk) if pk else None
    form = PCForm(request.POST if request.method == "POST" else None, instance=pc, owner=request.user)
    if request.method == "POST" and form.is_valid():
        pc = form.save()
        messages.success(request, "Les informations du PC ont été mises à jour." if pk else "Votre PC a bien été ajouté. Ses recommandations sont prêtes.")
        return redirect(pc)
    return render(request, "maintenance/pc_form.html", {"active_page": "pcs", "form": form, "pc": pc})


@login_required
def pc_delete(request, pk):
    pc = get_object_or_404(owned_pcs(request.user), pk=pk)
    if request.method == "POST":
        name = pc.name
        try:
            pc.delete()
        except ProtectedError:
            messages.error(request, "Ce PC possède des rendez-vous ou des documents associés. Sa fiche est conservée avec son historique.")
            return redirect(pc)
        messages.success(request, f"Le PC « {name} » a été supprimé.")
        return redirect("maintenance:pc_list")
    return render(request, "maintenance/pc_confirm_delete.html", {"active_page": "pcs", "pc": pc})


@login_required
def history(request):
    records = MaintenanceRecord.objects.filter(pc__owner=request.user).select_related("pc")
    pc_id = request.GET.get("pc", "")
    if pc_id.isdigit():
        records = records.filter(pc_id=int(pc_id))
    return render(request, "maintenance/history.html", {
        "active_page": "history", "records": Paginator(records, 12).get_page(request.GET.get("page")),
        "pcs": owned_pcs(request.user), "selected_pc": pc_id,
    })


@login_required
def recommendations(request):
    priority = request.GET.get("priority", "")
    recs = active_recommendations(request.user)
    counts = {"all": recs.count(), "high": recs.filter(rule__priority="high").count(), "medium": recs.filter(rule__priority="medium").count(), "low": recs.filter(rule__priority="low").count()}
    if priority in ("high", "medium", "low"):
        recs = recs.filter(rule__priority=priority)
    return render(request, "maintenance/recommendations.html", {
        "active_page": "recommendations", "recommendations": recs, "priority": priority, "counts": counts,
    })


@login_required
@require_POST
def analyze(request):
    refresh_all_recommendations(owned_pcs(request.user))
    messages.success(request, "L’analyse de vos PC a été actualisée à partir des règles de maintenance.")
    return redirect("maintenance:recommendations")
