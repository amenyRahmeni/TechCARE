from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from appointments.models import Technician
from .models import ComponentListing


def technician_access(view):
    @wraps(view)
    @login_required
    def guarded(request, *args, **kwargs):
        if not request.user.is_active or not (request.user.is_staff or Technician.objects.filter(user=request.user).exists()):
            raise PermissionDenied("Cet espace est réservé aux techniciens.")
        return view(request, *args, **kwargs)
    return guarded


def visible_listings(user):
    items = ComponentListing.objects.select_related("seller__user", "category")
    if user.is_staff:
        return items
    return items.filter(Q(status="published", seller__user__is_active=True) | Q(seller__user=user))


def can_edit_listing(user, listing):
    return user.is_active and (user.is_staff or listing.seller.user_id == user.pk)
