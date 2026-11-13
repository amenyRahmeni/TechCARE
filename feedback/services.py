from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Avg, Count

from appointments.models import Appointment
from appointments.permissions import is_technician_workspace
from repairs.models import RepairRequest
from notifications.models import Notification
from notifications.services import notify
from .models import Feedback


def source_queryset(kind):
    if kind == "appointment":
        return Appointment.objects.all()
    if kind == "repair":
        return RepairRequest.objects.all()
    raise ValidationError("Type d’intervention invalide.")


def technician_scores(technician):
    return Feedback.objects.filter(technician=technician).aggregate(average=Avg("rating"), count=Count("pk"))


@transaction.atomic
def submit_feedback(actor, kind, source_id, rating, comment):
    comment = comment.strip()
    if not 1 <= len(comment) <= 2000:
        raise ValidationError("Le commentaire doit contenir entre 1 et 2 000 caractères.")
    source = source_queryset(kind).select_for_update().get(pk=source_id)
    if not actor.is_authenticated or actor.is_staff or is_technician_workspace(actor) or source.client_id != actor.pk:
        raise PermissionDenied("Seul le client concerné peut évaluer cette réparation.")
    if source.status != ("completed" if kind == "appointment" else "resolved") or not source.technician_id:
        raise ValidationError("L’évaluation est disponible après la clôture de la réparation.")
    filters = {kind: source}
    if Feedback.objects.filter(**filters).exists():
        raise ValidationError("Vous avez déjà évalué cette réparation.")
    feedback = Feedback(client=actor, technician_id=source.technician_id, rating=rating, comment=comment, **filters)
    feedback.full_clean()
    feedback.save()
    notify(source.technician.user_id, kind=Notification.Kind.FEEDBACK, title="Un client a évalué votre intervention",
           message=f"Une nouvelle évaluation de {rating}/5 est disponible dans vos avis clients.",
           event_key=f"feedback:{feedback.pk}", **filters)
    return feedback
