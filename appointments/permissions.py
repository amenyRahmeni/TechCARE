from django.db.models import Q
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import Appointment, Invoice, Technician


def is_technician(user):
    return user.is_authenticated and Technician.objects.filter(user=user).exists()


def is_technician_workspace(user):
    return user.is_authenticated and not user.is_staff and is_technician(user)


def can_use_client_features(user):
    return user.is_authenticated and not is_technician_workspace(user)


def can_create_appointments(user):
    return user.is_authenticated and user.is_active and not user.is_staff and not is_technician_workspace(user)


def client_features_required(view):
    @wraps(view)
    @login_required
    def guarded(request, *args, **kwargs):
        if not can_use_client_features(request.user):
            raise PermissionDenied("Cette action appartient à l’espace client.")
        return view(request, *args, **kwargs)
    return guarded


def visible_appointments(user):
    queryset = Appointment.objects.all()
    if is_technician_workspace(user):
        return queryset.filter(technician__user=user)
    if not user.is_staff:
        queryset = queryset.filter(client=user)
    return queryset


def can_manage_intervention(user, appointment):
    return user.is_staff or appointment.technician.user_id == user.pk


def visible_invoices(user):
    queryset = Invoice.objects.all()
    if is_technician_workspace(user):
        return queryset.none()
    return queryset if user.is_staff else queryset.filter(Q(intervention__appointment__client=user) | Q(repair__client=user))
