from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import BookingSlot


def working_times():
    return [time(hour, 0) for hour in range(settings.APPOINTMENT_OPEN_HOUR, settings.APPOINTMENT_CLOSE_HOUR)]


def validate_start(starts_at):
    if timezone.is_naive(starts_at):
        raise ValidationError("Le créneau doit préciser le fuseau horaire.")
    local = timezone.localtime(starts_at)
    if starts_at <= timezone.now():
        raise ValidationError("Choisissez un créneau à venir.")
    if local.date() > timezone.localdate() + timedelta(days=365):
        raise ValidationError("Les réservations sont ouvertes pour les douze prochains mois.")
    if local.weekday() not in settings.APPOINTMENT_WORKING_DAYS:
        raise ValidationError("L’atelier est fermé le dimanche.")
    if local.time().replace(tzinfo=None) not in working_times():
        raise ValidationError("Choisissez un créneau d’une heure entre 09:00 et 18:00.")


def day_slots(technician, date, pc=None, exclude_appointment=None):
    start = timezone.make_aware(datetime.combine(date, time.min))
    end = start + timedelta(days=1)
    occupied = BookingSlot.objects.filter(starts_at__gte=start, starts_at__lt=end)
    if exclude_appointment:
        occupied = occupied.exclude(appointment_id=exclude_appointment.pk)
    technician_busy = set(occupied.filter(technician=technician).values_list("starts_at", flat=True))
    pc_busy = set(occupied.filter(pc=pc).values_list("starts_at", flat=True)) if pc else set()
    results = []
    for slot in working_times():
        begins = timezone.make_aware(datetime.combine(date, slot))
        valid = True
        try:
            validate_start(begins)
        except ValidationError:
            valid = False
        results.append({"value": slot.strftime("%H:%M"), "label": f"{slot:%H:%M} – {(begins + timedelta(hours=1)):%H:%M}", "available": valid and begins not in technician_busy and begins not in pc_busy})
    return results
