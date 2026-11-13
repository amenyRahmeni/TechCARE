from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from decimal import Decimal, InvalidOperation

from appointments.models import Technician
from .listing_forms import ListingForm
from .listing_services import change_listing_status, save_listing
from .models import Category, ComponentListing
from .permissions import can_edit_listing, technician_access, visible_listings


def context(request, **values):
    return {"workspace_base": "backoffice/base.html" if request.user.is_staff else "base.html", "active_page": "showcase", "can_post_listing": Technician.objects.filter(user=request.user).exists(), **values}


@never_cache
@technician_access
@require_GET
def catalog(request, mine=False):
    mine = mine or request.GET.get("mine") == "1"
    active = ComponentListing.objects.filter(status="published", seller__user__is_active=True)
    own = ComponentListing.objects.filter(seller__user=request.user)
    items = visible_listings(request.user) if request.user.is_staff else active.select_related("seller__user", "category")
    if mine:
        items = own.select_related("seller__user", "category")
    elif not request.user.is_staff:
        items = items.filter(status="published")
    state = request.GET.get("state", "")
    if (mine or request.user.is_staff) and state in ComponentListing.Status.values:
        items = items.filter(status=state)
    q = request.GET.get("q", "").strip()[:100]
    category = request.GET.get("category", "")[:60]
    seller = request.GET.get("seller", "")
    if q:
        items = items.filter(Q(title__icontains=q) | Q(brand__icontains=q) | Q(reference__icontains=q) | Q(description__icontains=q) | Q(location__icontains=q) | Q(seller__user__first_name__icontains=q) | Q(seller__user__last_name__icontains=q) | Q(seller__user__username__icontains=q))
    if category:
        items = items.filter(category__code=category)
    if seller:
        items = items.filter(seller_id=int(seller)) if seller.isdecimal() and len(seller) <= 18 else items.none()
    price_error = ""
    for key, lookup in (("min_price", "unit_price__gte"), ("max_price", "unit_price__lte")):
        raw = request.GET.get(key, "")[:20]
        if raw:
            try:
                value = Decimal(raw.replace(",", "."))
                if not value.is_finite() or not 0 <= value <= Decimal("9999999.999"):
                    raise ValueError
                items = items.filter(**{lookup: value})
            except (ValueError, InvalidOperation):
                price_error = "Indiquez un prix positif valide."
                items = items.none()
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "inventory/showcase.html", context(request, mine=mine, price_error=price_error, page_obj=Paginator(items, 12).get_page(request.GET.get("page")), page_query=params.urlencode(), q=q, category=category, seller=seller, state=state, statuses=ComponentListing.Status.choices, categories=Category.objects.all(), sellers=Technician.objects.filter(component_listings__status="published", user__is_active=True).select_related("user").distinct(), counts={"active": active.count(), "sellers": active.values("seller_id").distinct().count(), "mine": own.count()}))


@never_cache
@technician_access
@require_GET
def detail(request, pk):
    listing = get_object_or_404(visible_listings(request.user), pk=pk)
    others = ComponentListing.objects.filter(seller=listing.seller, status="published", seller__user__is_active=True).exclude(pk=pk).select_related("seller__user", "category")[:3]
    return render(request, "inventory/listing_detail.html", context(request, listing=listing, can_edit=can_edit_listing(request.user, listing), others=others))


@never_cache
@technician_access
def listing_form(request, pk=None):
    listing = get_object_or_404(visible_listings(request.user), pk=pk) if pk else None
    if listing and not can_edit_listing(request.user, listing):
        raise PermissionDenied
    if not listing and not Technician.objects.filter(user=request.user).exists():
        raise PermissionDenied("Un profil technicien est nécessaire pour déposer une annonce.")
    form = ListingForm(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None, instance=listing)
    if request.method == "POST" and form.is_valid():
        try:
            saved = save_listing(request.user, form.cleaned_data, pk=pk, draft=request.POST.get("action") == "draft")
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Votre annonce est enregistrée en brouillon." if saved.status == "draft" else "Votre annonce est publiée dans la vitrine des techniciens.")
            return redirect(saved)
    return render(request, "inventory/listing_form.html", context(request, form=form, listing=listing))


@technician_access
@require_POST
def status_update(request, pk):
    listing = get_object_or_404(visible_listings(request.user), pk=pk)
    try:
        change_listing_status(request.user, pk, request.POST.get("status", ""))
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Le statut de l’annonce a été mis à jour.")
    return redirect(listing)


@never_cache
@technician_access
@require_GET
def photo(request, pk):
    listing = get_object_or_404(visible_listings(request.user), pk=pk)
    if not listing.photo:
        raise Http404
    try:
        response = FileResponse(listing.photo.open("rb"), content_type="image/jpeg")
    except FileNotFoundError:
        raise Http404 from None
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = 'inline; filename="composant.jpg"'
    return response
