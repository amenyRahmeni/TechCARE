from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from appointments.models import Appointment
from appointments.permissions import is_technician
from maintenance.models import PC
from maintenance.permissions import viewable_pcs
from repairs.models import RepairRequest
from .compatibility import compatibility
from .forms import CategoryForm, ComponentForm, StockForm, UseForm
from .models import Category, ComponentUsage, SparePart, StockMovement
from .services import adjust_stock, return_component, use_component
from .permissions import technician_access


def context(request, **values):
    return {"active_page": "components", "workspace_base": "backoffice/base.html" if request.resolver_match.namespace == "backoffice" else "base.html", **values}


def private_pcs(user):
    return viewable_pcs(user)


@never_cache
@technician_access
@require_GET
def catalog(request):
    parts = SparePart.objects.select_related("category").all()
    if not request.user.is_staff:
        parts = parts.filter(is_active=True)
    counts = {"total": parts.count(), "available": parts.filter(stock__gt=0).count(), "low": parts.filter(stock__lte=F("low_stock_threshold")).count()}
    q = request.GET.get("q", "").strip()[:100]
    category = request.GET.get("category", "")[:60]
    brand = request.GET.get("brand", "")[:60]
    availability = request.GET.get("availability", "")
    if q:
        parts = parts.filter(Q(name__icontains=q) | Q(reference__icontains=q) | Q(description__icontains=q))
    if category:
        parts = parts.filter(category__code=category)
    if brand:
        parts = parts.filter(brand__iexact=brand)
    if availability == "available":
        parts = parts.filter(stock__gt=0)
    elif availability == "empty":
        parts = parts.filter(stock=0)
    elif availability == "low":
        parts = parts.filter(stock__lte=F("low_stock_threshold"))
    price_error = ""
    for key, lookup in (("min_price", "unit_price__gte"), ("max_price", "unit_price__lte")):
        raw = request.GET.get(key, "")[:20]
        if raw:
            try:
                value = Decimal(raw.replace(",", "."))
                if not value.is_finite() or not 0 <= value <= Decimal("9999999.999"):
                    raise ValueError
                parts = parts.filter(**{lookup: value})
            except (ValueError, InvalidOperation):
                price_error = "Indiquez un prix positif valide."
                parts = parts.none()
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "inventory/catalog.html", context(request, page_obj=Paginator(parts, 12).get_page(request.GET.get("page")), page_query=params.urlencode(), categories=Category.objects.all(), brands=SparePart.objects.filter(is_active=True).values_list("brand", flat=True).distinct().order_by("brand"), counts=counts, q=q, category=category, brand=brand, availability=availability, price_error=price_error))


@never_cache
@technician_access
@require_GET
def detail(request, pk):
    part = get_object_or_404(SparePart.objects.select_related("category"), pk=pk)
    if not part.is_active and not request.user.is_staff:
        raise Http404
    pcs = private_pcs(request.user)
    selected_pc = request.GET.get("pc", "")
    pc, issues = None, None
    if selected_pc:
        if not selected_pc.isdecimal() or len(selected_pc) > 18:
            raise Http404
        pc = get_object_or_404(pcs, pk=int(selected_pc))
        issues = compatibility(part, pc)
    manager = request.user.is_staff or is_technician(request.user)
    usages = part.usages.select_related("repair__pc", "appointment__pc", "used_by")
    if not request.user.is_staff:
        usages = usages.filter(Q(repair__client=request.user) | Q(repair__technician__user=request.user) | Q(appointment__client=request.user) | Q(appointment__technician__user=request.user))
    return render(request, "inventory/detail.html", context(request, component=part, pcs=pcs, selected_pc=pc, compatibility_issues=issues, compatibility_checked=pc is not None, stock_form=StockForm(), use_form=UseForm(actor=request.user, initial={"component": part.pk}), stock_manager=manager, usages=usages[:20]))


@login_required
def component_form(request, pk=None):
    if not request.user.is_staff:
        raise PermissionDenied
    part = get_object_or_404(SparePart, pk=pk) if pk else None
    with transaction.atomic():
        if part and request.method == "POST":
            part = SparePart.objects.select_for_update().get(pk=pk)
        form = ComponentForm(request.POST if request.method == "POST" else None, instance=part)
        if request.method == "POST" and form.is_valid():
            saved = form.save()
            opening = form.cleaned_data.get("opening_stock") or 0
            if not pk and opening:
                adjust_stock(request.user, saved.pk, opening, "Stock initial à la création")
            messages.success(request, "Le composant a été enregistré.")
            return redirect("backoffice:component_detail", pk=saved.pk)
    return render(request, "inventory/form.html", context(request, form=form, title="Modifier le composant" if pk else "Ajouter un composant", subtitle="Prix, catalogue et contraintes de compatibilité."))


@login_required
@require_POST
def stock_adjust(request, pk):
    if not request.user.is_staff:
        raise PermissionDenied
    part = get_object_or_404(SparePart, pk=pk)
    form = StockForm(request.POST)
    if form.is_valid():
        try:
            adjust_stock(request.user, pk, form.cleaned_data["delta"], form.cleaned_data["reason"])
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "Mouvement de stock enregistré.")
    else:
        messages.error(request, "Indiquez une variation entière et un motif.")
    return redirect("backoffice:component_detail", pk=part.pk)


@login_required
@require_POST
def consume(request):
    if not (request.user.is_staff or is_technician(request.user)):
        raise PermissionDenied
    form = UseForm(request.POST, actor=request.user)
    if not form.is_valid():
        messages.error(request, "Vérifiez le composant, la quantité et l’intervention sélectionnée.")
        return redirect("inventory:catalog")
    kind, pk = form.cleaned_data["target"].split(":")
    try:
        use_component(request.user, component_id=form.cleaned_data["component"].pk, quantity=form.cleaned_data["quantity"], token=form.cleaned_data["token"], **{f"{kind}_id": int(pk)})
    except (RepairRequest.DoesNotExist, Appointment.DoesNotExist):
        raise Http404 from None
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Composant ajouté : stock décrémenté et coût enregistré.")
    if kind == "repair":
        return redirect("backoffice:repair_detail" if request.user.is_staff else "repairs:detail", pk=pk)
    return redirect("backoffice:detail" if request.user.is_staff else "appointments:detail", pk=pk)


@login_required
@require_POST
def usage_return(request, pk):
    usage = get_object_or_404(ComponentUsage, pk=pk)
    try:
        return_component(request.user, pk, request.POST.get("reason", "")[:250])
    except (RepairRequest.DoesNotExist, Appointment.DoesNotExist):
        raise Http404 from None
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Composant retourné au stock.")
    if usage.repair_id:
        return redirect("backoffice:repair_detail" if request.user.is_staff else "repairs:detail", pk=usage.repair_id)
    return redirect("backoffice:detail" if request.user.is_staff else "appointments:detail", pk=usage.appointment_id)


@never_cache
@login_required
@require_GET
def movements(request):
    if not (request.user.is_staff or is_technician(request.user)):
        raise PermissionDenied
    rows = StockMovement.objects.select_related("component", "actor", "usage__repair", "usage__appointment")
    q = request.GET.get("q", "").strip()[:100]
    kind = request.GET.get("kind", "")
    if q:
        rows = rows.filter(Q(component__name__icontains=q) | Q(component__reference__icontains=q) | Q(reason__icontains=q))
    if kind in StockMovement.Kind.values:
        rows = rows.filter(kind=kind)
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "inventory/movements.html", context(request, active_page="stock", page_obj=Paginator(rows, 20).get_page(request.GET.get("page")), page_query=params.urlencode(), q=q, kind=kind, kinds=StockMovement.Kind.choices))


@login_required
def categories(request, pk=None):
    if not request.user.is_staff:
        raise PermissionDenied
    category = get_object_or_404(Category, pk=pk) if pk else None
    form = CategoryForm(request.POST if request.method == "POST" else None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Catégorie enregistrée.")
        return redirect("backoffice:categories")
    return render(request, "inventory/categories.html", context(request, form=form, categories=Category.objects.all(), category=category))
