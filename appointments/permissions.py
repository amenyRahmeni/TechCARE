from django.db.models import Q

from .models import Appointment, Invoice, Technician


def is_technician(user):
    return user.is_authenticated and Technician.objects.filter(user=user).exists()


def visible_appointments(user):
    queryset = Appointment.objects.all()
    if not user.is_staff:
        queryset = queryset.filter(Q(client=user) | Q(technician__user=user))
    return queryset


def can_manage_intervention(user, appointment):
    return user.is_staff or appointment.technician.user_id == user.pk


def visible_invoices(user):
    queryset = Invoice.objects.all()
    return queryset if user.is_staff else queryset.filter(intervention__appointment__client=user)
