from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from maintenance.models import MaintenanceRecord, PC
from .models import Appointment, BookingSlot, Intervention, Invoice, PartLine, Technician
from .permissions import can_manage_intervention, visible_appointments
from .scheduling import validate_start

TRANSITIONS = {
    Appointment.Status.PENDING: (Appointment.Status.CONFIRMED, Appointment.Status.CANCELLED),
    Appointment.Status.CONFIRMED: (Appointment.Status.DIAGNOSIS, Appointment.Status.CANCELLED),
    Appointment.Status.DIAGNOSIS: (Appointment.Status.REPAIR, Appointment.Status.COMPLETED, Appointment.Status.CANCELLED),
    Appointment.Status.REPAIR: (Appointment.Status.COMPLETED,),
    Appointment.Status.COMPLETED: (),
    Appointment.Status.CANCELLED: (),
}


def _slot_error():
    return ValidationError("Ce créneau n’est plus disponible pour le technicien ou pour ce PC. Choisissez un autre horaire.")


def _reserve(appointment):
    validate_start(appointment.starts_at)
    if not appointment.technician.is_available or not appointment.technician.user.is_active:
        raise ValidationError("Ce technicien n’accepte pas de nouveaux rendez-vous.")
    conflict = BookingSlot.objects.filter(starts_at=appointment.starts_at).exclude(appointment=appointment)
    if conflict.filter(technician=appointment.technician).exists() or conflict.filter(pc=appointment.pc).exists():
        raise _slot_error()
    BookingSlot.objects.update_or_create(appointment=appointment, defaults={"technician": appointment.technician, "pc": appointment.pc, "starts_at": appointment.starts_at})


def book_appointment(actor, data, appointment_id=None):
    try:
        with transaction.atomic():
            if appointment_id:
                appointment = visible_appointments(actor).select_for_update(of=("self",)).get(pk=appointment_id)
                if not appointment.can_modify:
                    raise ValidationError("La modification est impossible pendant la réparation ou après la clôture.")
                if data["pc"].owner_id != appointment.client_id:
                    raise ValidationError("L’ordinateur doit appartenir au client du rendez-vous.")
                if not actor.is_staff and actor.pk != appointment.client_id and data["pc"].pk != appointment.pc_id:
                    raise PermissionDenied
            else:
                if not actor.is_staff and data["pc"].owner_id != actor.pk:
                    raise PermissionDenied
                appointment = Appointment(client=data["pc"].owner)
            technician_ids = {data["technician"].pk}
            pc_ids = {data["pc"].pk}
            if appointment.pk:
                technician_ids.add(appointment.technician_id)
                pc_ids.add(appointment.pc_id)
            # Deterministic lock order plus unique indexes protects concurrent bookings.
            technicians = {tech.pk: tech for tech in Technician.objects.select_for_update().filter(pk__in=sorted(technician_ids)).order_by("pk")}
            pcs = {pc.pk: pc for pc in PC.objects.select_for_update().filter(pk__in=sorted(pc_ids)).order_by("pk")}
            appointment.technician = technicians[data["technician"].pk]
            appointment.pc = pcs[data["pc"].pk]
            if appointment.pc.owner_id != appointment.client_id:
                raise ValidationError("Le propriétaire de cet ordinateur a changé. Rechargez le formulaire.")
            for field in ("starts_at", "category", "reason", "description"):
                setattr(appointment, field, data[field])
            appointment.status = Appointment.Status.PENDING
            appointment.full_clean()
            appointment.save()
            _reserve(appointment)
            Intervention.objects.get_or_create(appointment=appointment)
            return appointment
    except IntegrityError as error:
        if error.args and error.args[0] == 1062:
            raise _slot_error() from error
        raise


@transaction.atomic
def cancel_appointment(actor, appointment_id):
    appointment = visible_appointments(actor).select_for_update(of=("self",)).get(pk=appointment_id)
    if not appointment.can_modify:
        raise ValidationError("L’annulation est impossible pendant la réparation ou après la clôture.")
    appointment.status = Appointment.Status.CANCELLED
    appointment.save(update_fields=["status", "updated_at"])
    BookingSlot.objects.filter(appointment=appointment).delete()
    return appointment


def _close_intervention(appointment):
    intervention, _ = Intervention.objects.get_or_create(appointment=appointment)
    if not intervention.diagnosis.strip() or not intervention.solution.strip():
        raise ValidationError("Renseignez le diagnostic et les travaux réalisés avant de terminer l’intervention.")
    if intervention.completed_at:
        return
    pc = PC.objects.select_for_update().get(pk=appointment.pc_id)
    completed = timezone.now()
    kind = {"preventive": "preventive", "upgrade": "upgrade"}.get(appointment.category, "repair")
    record = MaintenanceRecord.objects.create(
        pc=pc, title=appointment.reason, kind=kind,
        description=f"Diagnostic :\n{intervention.diagnosis}\n\nTravaux réalisés :\n{intervention.solution}",
        completed_on=timezone.localdate(completed), technician=str(appointment.technician),
    )
    intervention.maintenance_record = record
    intervention.completed_at = completed
    intervention.save()
    parts = [{"name": part.name, "quantity": part.quantity, "unit_price": str(part.unit_price), "total": str(part.total)} for part in intervention.parts.all()]
    total = intervention.total_amount.quantize(Decimal("0.001"))
    snapshot = {
        "appointment_id": appointment.pk,
        "scheduled_at": timezone.localtime(appointment.starts_at).isoformat(),
        "completed_at": timezone.localtime(completed).isoformat(),
        "client": appointment.client.get_full_name() or appointment.client.username,
        "client_email": appointment.client.email,
        "technician": str(appointment.technician), "reason": appointment.reason,
        "category": appointment.get_category_display(),
        "pc": {"name": pc.name, "brand": pc.brand, "model": pc.model, "serial_number": pc.serial_number or "", "operating_system": pc.operating_system, "processor": pc.processor, "ram_gb": pc.ram_gb, "storage_gb": pc.storage_gb, "storage_type": pc.storage_type},
        "diagnosis": intervention.diagnosis, "solution": intervention.solution,
        "parts": parts, "parts_total": str(intervention.parts_total),
        "labour_cost": str(intervention.labour_cost), "total": str(total), "currency": "TND",
    }
    Invoice.objects.create(intervention=intervention, snapshot=snapshot, total_amount=total, issued_at=completed)


def _transition(appointment, status):
    if status == appointment.status:
        return
    if status not in TRANSITIONS.get(appointment.status, ()):
        raise ValidationError("Ce changement de statut n’est pas autorisé à cette étape.")
    if status == Appointment.Status.COMPLETED:
        _close_intervention(appointment)
    if status == Appointment.Status.CANCELLED:
        BookingSlot.objects.filter(appointment=appointment).delete()
    appointment.status = status
    appointment.save(update_fields=["status", "updated_at"])


@transaction.atomic
def update_status(actor, appointment_id, status):
    appointment = visible_appointments(actor).select_for_update(of=("self",)).get(pk=appointment_id)
    if not can_manage_intervention(actor, appointment):
        raise PermissionDenied
    _transition(appointment, status)
    return appointment


@transaction.atomic
def save_intervention(actor, appointment_id, data, parts, complete=False):
    appointment = visible_appointments(actor).select_for_update(of=("self",)).get(pk=appointment_id)
    if not can_manage_intervention(actor, appointment):
        raise PermissionDenied
    if appointment.is_closed:
        raise ValidationError("Cette intervention est clôturée. Son compte rendu et sa facture sont conservés en lecture seule.")
    intervention, _ = Intervention.objects.get_or_create(appointment=appointment)
    for field in ("diagnosis", "solution", "labour_cost"):
        setattr(intervention, field, data[field])
    intervention.full_clean()
    intervention.save()
    if len(parts) > 20:
        raise ValidationError("Vous pouvez renseigner au maximum 20 lignes de pièces.")
    intervention.parts.all().delete()
    for line in parts:
        part = PartLine(intervention=intervention, **line)
        part.full_clean()
        part.save()
    if complete:
        _transition(appointment, Appointment.Status.COMPLETED)
    return appointment
