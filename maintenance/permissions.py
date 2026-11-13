from django.db.models import Q

from appointments.permissions import is_technician_workspace
from .models import PC


def viewable_pcs(user):
    if user.is_staff:
        return PC.objects.all()
    if is_technician_workspace(user):
        return PC.objects.filter(Q(appointments__technician__user=user) | Q(repair_requests__technician__user=user)).distinct()
    return PC.objects.filter(owner=user)
