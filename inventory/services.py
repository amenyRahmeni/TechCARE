from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from appointments.models import Appointment, PartLine
from appointments.permissions import can_manage_intervention, visible_appointments
from maintenance.models import PC
from notifications.models import Notification
from notifications.services import notify
from repairs.models import RepairRequest
from repairs.permissions import can_manage, visible_repairs
from .compatibility import compatibility
from .models import ComponentUsage, SparePart, StockMovement


def _stock_alert(part, movement, recipients=()):
    if part.stock <= part.low_stock_threshold:
        ids = set(get_user_model().objects.filter(is_staff=True, is_active=True).values_list("pk", flat=True)) | set(recipients)
        for recipient in ids:
            notify(recipient, kind=Notification.Kind.COMPONENT, level="warning", title="Stock de composant à surveiller", message=f"{part.name} ({part.reference}) : {part.stock} unité(s) disponible(s), seuil {part.low_stock_threshold}.", event_key=f"low-stock:{movement.pk}", component=part)


@transaction.atomic
def adjust_stock(actor, component_id, delta, reason):
    if not actor.is_active or not actor.is_staff:
        raise PermissionDenied
    if not isinstance(delta, int) or delta == 0 or not reason.strip():
        raise ValidationError("Indiquez une variation non nulle et un motif.")
    part = SparePart.objects.select_for_update().get(pk=component_id)
    if not 0 <= part.stock + delta <= 100000:
        raise ValidationError("L’ajustement doit conserver un stock entre 0 et 100 000.")
    part.stock += delta
    part.save(update_fields=["stock", "updated_at"])
    movement = StockMovement.objects.create(component=part, kind="entry", delta=delta, stock_after=part.stock, actor=actor, reason=reason[:250])
    _stock_alert(part, movement)
    return movement


def _target(actor, *, repair_id=None, appointment_id=None, allow_closed=False):
    if bool(repair_id) == bool(appointment_id):
        raise ValidationError("Choisissez une seule réparation ou intervention.")
    if repair_id:
        target = visible_repairs(actor).select_for_update(of=("self",)).select_related("pc", "technician").get(pk=repair_id)
        allowed = can_manage(actor, target)
        ready = target.status in ("diagnosis", "repair", "waiting")
    else:
        target = visible_appointments(actor).select_for_update(of=("self",)).select_related("pc", "technician").get(pk=appointment_id)
        allowed = can_manage_intervention(actor, target)
        ready = target.status in ("diagnosis", "repair")
    if not allowed or not actor.is_active:
        raise PermissionDenied
    if not allow_closed and not ready:
        raise ValidationError("Les composants s’utilisent pendant le diagnostic ou la réparation.")
    return target


@transaction.atomic
def use_component(actor, *, component_id, quantity, token, repair_id=None, appointment_id=None):
    target = _target(actor, repair_id=repair_id, appointment_id=appointment_id)
    existing = ComponentUsage.objects.filter(token=token).first()
    if existing:
        if (existing.used_by_id, existing.component_id, existing.quantity, existing.repair_id, existing.appointment_id) != (actor.pk, component_id, quantity, repair_id, appointment_id):
            raise ValidationError("Cette validation a déjà été utilisée pour une autre action.")
        return existing
    part = SparePart.objects.select_for_update().get(pk=component_id)
    if not isinstance(quantity, int) or not 1 <= quantity <= 1000:
        raise ValidationError("La quantité doit être comprise entre 1 et 1 000.")
    if not part.is_active:
        raise ValidationError("Ce composant est archivé.")
    # Lock the PC to check the same declared configuration throughout validation.
    pc = PC.objects.select_for_update().get(pk=target.pc_id)
    issues = compatibility(part, pc)
    if issues:
        raise ValidationError(issues)
    if part.stock < quantity:
        raise ValidationError(f"Stock insuffisant : {part.stock} unité(s) disponible(s). La sortie n’a pas été enregistrée.")
    usage = ComponentUsage.objects.create(component=part, quantity=quantity, unit_price=part.unit_price, name_snapshot=f"{part.name} · {part.reference}", used_by=actor, token=token, repair_id=repair_id, appointment_id=appointment_id)
    part.stock -= quantity
    part.save(update_fields=["stock", "updated_at"])
    movement = StockMovement.objects.create(component=part, kind="use", delta=-quantity, stock_after=part.stock, actor=actor, usage=usage, reason=f"Utilisation pour {'REP-' + str(target.pk) if repair_id else 'RDV #' + str(target.pk)}")
    if appointment_id:
        PartLine.objects.create(intervention=target.intervention, stock_usage=usage, name=usage.name_snapshot[:150], quantity=quantity, unit_price=part.unit_price)
    else:
        from repairs.services import event
        event(target, actor, "Composant utilisé", f"{quantity} × {usage.name_snapshot}")
    _stock_alert(part, movement, [actor.pk])
    return usage


def _return_locked(actor, usage, reason):
    if usage.returned_at:
        return usage
    part = SparePart.objects.select_for_update().get(pk=usage.component_id)
    if part.stock + usage.quantity > 100000:
        raise ValidationError("Le retour dépasserait la limite de stock. Vérifiez l’inventaire.")
    part.stock += usage.quantity
    part.save(update_fields=["stock", "updated_at"])
    usage.returned_at, usage.return_reason = timezone.now(), reason[:250]
    usage.save(update_fields=["returned_at", "return_reason"])
    StockMovement.objects.create(component=part, kind="return", delta=usage.quantity, stock_after=part.stock, actor=actor, usage=usage, reason=reason[:250])
    PartLine.objects.filter(stock_usage=usage).delete()
    return usage


@transaction.atomic
def return_component(actor, usage_id, reason):
    if not reason.strip():
        raise ValidationError("Indiquez le motif du retour.")
    initial = ComponentUsage.objects.get(pk=usage_id)
    _target(actor, repair_id=initial.repair_id, appointment_id=initial.appointment_id)
    usage = ComponentUsage.objects.select_for_update().get(pk=usage_id)
    if usage.returned_at:
        return usage
    result = _return_locked(actor, usage, reason)
    if usage.repair_id:
        from repairs.services import event
        event(usage.repair, actor, "Composant retourné au stock", reason)
    return result


def return_target_components(actor, *, repair=None, appointment=None, reason):
    # Caller holds the target lock and owns the surrounding transaction.
    usages = ComponentUsage.objects.select_for_update().filter(repair=repair) if repair else ComponentUsage.objects.select_for_update().filter(appointment=appointment)
    for usage in usages.filter(returned_at__isnull=True).order_by("component_id", "pk"):
        _return_locked(actor, usage, reason)
