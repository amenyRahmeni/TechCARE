from django.db.models import Q
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import RepairRequest
from appointments.permissions import is_technician_workspace


def can_access_repairs(user):
    return user.is_authenticated and user.is_active and not user.is_staff


def can_create_repair_requests(user):
    return can_access_repairs(user) and not is_technician_workspace(user)


def repair_access_required(view):
    @wraps(view)
    @login_required
    def guarded(request, *args, **kwargs):
        if not can_access_repairs(request.user):
            raise PermissionDenied("L’assistance et les réparations sont réservées aux clients et aux techniciens concernés.")
        return view(request, *args, **kwargs)
    return guarded


def qualified_technicians(problem):
    from appointments.models import Technician
    if problem not in RepairRequest.Problem.values:
        return Technician.objects.none()
    skill = RepairRequest(problem=problem).required_skill
    candidates = Technician.objects.filter(is_available=True, user__is_active=True, user__is_staff=False).select_related("user")
    return candidates.filter(pk__in=[tech.pk for tech in candidates if skill in tech.skills])


def visible_repairs(user):
    items = RepairRequest.objects.all()
    if not can_access_repairs(user):
        return items.none()
    if is_technician_workspace(user):
        return items.filter(technician__user=user)
    return items.filter(Q(client=user) | Q(technician__user=user))


def can_manage(user, repair):
    return can_access_repairs(user) and bool(repair.technician_id and repair.technician.user_id == user.pk)
