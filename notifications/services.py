from datetime import datetime, time, timedelta
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Notification, PushDelivery, PushSubscription

K = Notification.Kind
L = Notification.Level


@transaction.atomic
def notify(recipient_id, *, kind, title, message, event_key, level=L.INFO, appointment=None, recommendation=None, repair=None, component=None, campaign=None, expires_at=None):
    if not get_user_model().objects.filter(pk=recipient_id, is_active=True).exists():
        return None
    notification, created = Notification.objects.get_or_create(recipient_id=recipient_id, event_key=event_key, defaults={"kind": kind, "level": level, "title": title[:150], "message": message[:700], "appointment": appointment, "recommendation": recommendation, "repair": repair, "component": component, "campaign": campaign, "expires_at": expires_at})
    if created:
        PushDelivery.objects.bulk_create([PushDelivery(notification=notification, subscription_id=pk) for pk in PushSubscription.objects.filter(user_id=recipient_id, is_active=True).values_list("pk", flat=True)])
    return notification


def participants(appointment):
    return {appointment.client_id, appointment.technician.user_id}


def date_label(appointment):
    return timezone.localtime(appointment.starts_at).strftime("%d/%m/%Y à %H:%M")


def expire_reminders(appointment):
    stale = Notification.objects.filter(appointment=appointment, kind=K.REMINDER)
    stale.update(expires_at=timezone.now())
    PushDelivery.objects.filter(notification__in=stale, state=PushDelivery.State.PENDING).update(state=PushDelivery.State.CANCELLED)


def notify_booking(appointment, previous=None):
    if previous is None:
        notify(appointment.client_id, kind=K.BOOKING, title="Votre demande de rendez-vous est enregistrée", message=f"{appointment.pc.name} : le {date_label(appointment)} avec {appointment.technician}. Vous recevrez sa confirmation.", event_key=f"booking:{appointment.pk}", appointment=appointment)
        notify(appointment.technician.user_id, kind=K.ASSIGNMENT, title="Un rendez-vous vous a été assigné", message=f"{appointment.pc.name} : {appointment.reason}, le {date_label(appointment)}. Consultez la demande pour la confirmer.", event_key=f"assignment:{appointment.pk}:initial", appointment=appointment)
        return
    expire_reminders(appointment)
    event = f"updated:{appointment.pk}:{uuid.uuid4().hex}"
    for recipient_id in participants(appointment) | {previous["technician_user_id"]}:
        released = recipient_id == previous["technician_user_id"] and recipient_id not in participants(appointment)
        notify(recipient_id, kind=K.UPDATED, title="Un rendez-vous a été modifié", message=(f"Le rendez-vous pour {appointment.pc.name}, précédemment prévu le {previous['label']}, a été réaffecté à un autre technicien." if released else f"{appointment.pc.name} : nouveau rendez-vous le {date_label(appointment)} avec {appointment.technician}. Une nouvelle confirmation est nécessaire."), event_key=event, appointment=appointment, level=L.WARNING)


def notify_status(appointment):
    if appointment.status == "cancelled":
        expire_reminders(appointment)
        for recipient_id in participants(appointment):
            notify(recipient_id, kind=K.CANCELLED, title="Un rendez-vous a été annulé", message=f"Le rendez-vous pour {appointment.pc.name}, prévu le {date_label(appointment)}, est annulé. Le créneau a été libéré.", event_key=f"cancelled:{appointment.pk}", appointment=appointment, level=L.WARNING)
        return
    kind = K.CONFIRMED if appointment.status == "confirmed" else K.STATUS
    title = {"confirmed": "Votre rendez-vous est confirmé", "diagnosis": "Le diagnostic de votre PC a commencé", "repair": "Votre PC est en réparation", "completed": "L’intervention sur votre PC est terminée"}.get(appointment.status)
    if not title:
        return
    notify(appointment.client_id, kind=kind, title=title, message=f"{appointment.pc.name} : {appointment.get_status_display().lower()}. Rendez-vous du {date_label(appointment)} avec {appointment.technician}.", event_key=f"status:{appointment.pk}:{appointment.status}:{appointment.updated_at.isoformat()}", appointment=appointment, level=L.SUCCESS if appointment.status in ("confirmed", "completed") else L.INFO)
    if appointment.status == "completed":
        expire_reminders(appointment)
        notify(appointment.client_id, kind=K.DOCUMENTS, title="Votre rapport et votre facture sont disponibles", message=f"Les documents PDF de l’intervention sur {appointment.pc.name} sont prêts. Retrouvez-les dans le suivi ou dans Rapports & factures.", event_key=f"documents:{appointment.pk}", appointment=appointment, level=L.SUCCESS)


def notify_recommendation(recommendation):
    from appointments.permissions import can_use_client_features
    if not can_use_client_features(recommendation.pc.owner):
        return
    notify(recommendation.pc.owner_id, kind=K.RECOMMENDATION, title=recommendation.rule.title, message=f"{recommendation.pc.name} : {recommendation.reason} Conseil de maintenance, aide à la décision.", event_key=f"recommendation:{recommendation.pk}:{recommendation.updated_at.isoformat()}", recommendation=recommendation, level=L.WARNING if recommendation.rule.priority == "high" else L.INFO)


def sync_current_recommendations():
    """Bring existing active advice into the new inbox once, preserving read state."""
    from maintenance.models import Recommendation
    for pk in Recommendation.objects.filter(is_active=True, rule__is_active=True).order_by("pk").values_list("pk", flat=True).iterator():
        with transaction.atomic():
            recommendation = Recommendation.objects.select_for_update(of=("self",)).select_related("pc", "rule").get(pk=pk)
            if recommendation.is_active and recommendation.rule.is_active and not Notification.objects.current().filter(recommendation=recommendation, kind=K.RECOMMENDATION).exists():
                notify_recommendation(recommendation)


def reminder_key(appointment):
    return f"reminder:{appointment.pk}:{appointment.starts_at.isoformat()}"


def generate_reminders(now=None):
    from appointments.models import Appointment
    now = now or timezone.now()
    tomorrow = timezone.localtime(now).date() + timedelta(days=1)
    start = timezone.make_aware(datetime.combine(tomorrow, time.min))
    end = timezone.make_aware(datetime.combine(tomorrow + timedelta(days=1), time.min))
    count = 0
    ids = Appointment.objects.filter(status="confirmed", starts_at__gte=start, starts_at__lt=end).order_by("pk").values_list("pk", flat=True)
    for pk in ids.iterator():
        with transaction.atomic():
            appointment = Appointment.objects.select_for_update(of=("self",)).select_related("pc", "technician__user").get(pk=pk)
            if appointment.status != "confirmed" or not start <= appointment.starts_at < end:
                continue
            key = reminder_key(appointment)
            for recipient_id in participants(appointment):
                exists = Notification.objects.filter(recipient_id=recipient_id, event_key=key).exists()
                result = notify(recipient_id, kind=K.REMINDER, title="Rappel : votre rendez-vous est demain", message=f"{appointment.pc.name} : rendez-vous le {date_label(appointment)} avec {appointment.technician}. Horaires de Tunis.", event_key=key, appointment=appointment, expires_at=appointment.starts_at, level=L.WARNING)
                count += bool(result and not exists)
    return count


def notify_message_received(*, recipient_id, sender_id, appointment, message_id):
    """Notify participants of a persisted intervention message."""
    allowed = participants(appointment)
    if recipient_id not in allowed or sender_id not in allowed or recipient_id == sender_id:
        raise ValidationError("Le message doit concerner les participants de l’intervention.")
    return notify(recipient_id, kind=K.MESSAGE, title="Vous avez reçu un nouveau message", message=f"Un nouveau message concerne l’intervention sur {appointment.pc.name}.", event_key=f"message:{message_id}", appointment=appointment)


def notify_component_unavailable(*, appointment, component_name, event_id):
    """Integration hook to call when the future stock module detects a shortage."""
    recipients = {appointment.technician.user_id, *get_user_model().objects.filter(is_staff=True, is_active=True).values_list("pk", flat=True)}
    return [notify(pk, kind=K.COMPONENT, title="Une pièce nécessaire est indisponible", message=f"Intervention sur {appointment.pc.name} : {component_name[:150]}. Une vérification de la prise en charge est nécessaire.", event_key=f"component:{appointment.pk}:{event_id}", appointment=appointment, level=L.WARNING) for pk in recipients]
