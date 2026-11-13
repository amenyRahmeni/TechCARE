from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from notifications.models import Notification
from notifications.services import notify
from .models import Appointment, AppointmentMessage
from .permissions import visible_appointments


@transaction.atomic
def send_message(actor, appointment_id, body):
    appointment = Appointment.objects.select_for_update().select_related("technician__user").get(pk=appointment_id)
    if not actor.is_authenticated or not visible_appointments(actor).filter(pk=appointment_id).exists():
        raise PermissionDenied
    if appointment.is_closed:
        raise ValidationError("La discussion est en lecture seule après la clôture.")
    body = body.strip()
    if not 1 <= len(body) <= 2000:
        raise ValidationError("Le message doit contenir entre 1 et 2 000 caractères.")
    message = AppointmentMessage.objects.create(appointment=appointment, sender=actor, body=body)
    for recipient in {appointment.client_id, appointment.technician.user_id} - {actor.pk}:
        notify(recipient, kind=Notification.Kind.MESSAGE, title="Vous avez reçu un nouveau message",
               message=f"Un nouveau message concerne le rendez-vous #{appointment.pk} pour {appointment.pc.name}.",
               event_key=f"appointment-message:{message.pk}", appointment=appointment)
    return message
