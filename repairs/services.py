from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from appointments.models import Invoice, Technician
from maintenance.models import MaintenanceRecord, PC
from notifications.models import Notification
from notifications.services import notify
from .models import RepairEvent, RepairMessage, RepairRequest
from .permissions import can_create_repair_requests, can_manage, visible_repairs

S = RepairRequest.Status
TRANSITIONS = {S.SENT: [S.CANCELLED], S.ASSIGNED: [S.DIAGNOSIS, S.CANCELLED], S.DIAGNOSIS: [S.REPAIR, S.WAITING, S.RESOLVED, S.CANCELLED], S.REPAIR: [S.WAITING, S.RESOLVED, S.CANCELLED], S.WAITING: [S.DIAGNOSIS, S.REPAIR, S.CANCELLED], S.RESOLVED: [], S.CANCELLED: []}


def event(repair, actor, title, detail=""):
    return RepairEvent.objects.create(repair=repair, actor=actor, title=title, detail=detail[:700])


def alert(repair, recipients, title, message, key, kind=Notification.Kind.STATUS, level="info"):
    allowed = get_user_model().objects.filter(pk__in=set(recipients), is_active=True, is_staff=False).values_list("pk", flat=True)
    for recipient in allowed:
        if recipient:
            notify(recipient, kind=kind, title=title, message=message, event_key=key, repair=repair, level=level)


def create_request(actor, data):
    if not can_create_repair_requests(actor):
        raise PermissionDenied("La déclaration d’une panne appartient à l’espace client.")
    repair = None
    try:
        with transaction.atomic():
            pc = PC.objects.select_for_update().get(pk=data["pc"].pk)
            if pc.owner_id != actor.pk:
                raise PermissionDenied
            technician = data.get("technician")
            if technician is None:
                raise ValidationError("Choisissez un technicien qualifié pour cette panne.")
            repair = RepairRequest(client=pc.owner, pc=pc, **{key: data[key] for key in ("problem", "description", "technical_notes")})
            repair.full_clean(exclude=["photo"])
            if data.get("photo"):
                repair.photo = data["photo"]
            repair.save()
            created = event(repair, actor, "Demande envoyée", repair.get_problem_display())
            assign_technician(actor, repair.pk, technician.pk)
            repair.refresh_from_db()
            alert(repair, [repair.client_id], "Votre demande de réparation est enregistrée", f"{repair.reference} · {pc.name} : {repair.get_problem_display()}.", f"repair-created:{created.pk}")
            return repair
    except Exception:
        if repair and repair.photo and repair.photo._committed:
            repair.photo.storage.delete(repair.photo.name)
        raise


@transaction.atomic
def assign_technician(actor, repair_id, technician_id):
    if not can_create_repair_requests(actor):
        raise PermissionDenied
    repair = RepairRequest.objects.select_for_update().select_related("pc", "technician__user").get(pk=repair_id)
    if repair.client_id != actor.pk:
        raise PermissionDenied
    if repair.is_closed:
        raise ValidationError("Cette demande est clôturée.")
    if repair.status not in (S.SENT, S.ASSIGNED):
        raise ValidationError("Le choix du technicien ne peut plus être modifié après le début du diagnostic.")
    technician = Technician.objects.select_for_update().select_related("user").get(pk=technician_id)
    if not technician.user.is_active or technician.user.is_staff or not technician.is_available:
        raise ValidationError("Ce technicien n’accepte pas de nouvelles demandes.")
    if repair.required_skill not in technician.skills:
        raise ValidationError("Ce technicien ne possède pas la compétence requise pour cette panne.")
    if repair.technician_id == technician.pk:
        return repair
    if repair.status == S.REPAIR:
        raise ValidationError("La réaffectation est impossible pendant la réparation. Mettez d’abord la demande en attente.")
    old_user = repair.technician.user_id if repair.technician_id else None
    repair.technician = technician
    if repair.status == S.SENT:
        repair.status = S.ASSIGNED
    repair.save(update_fields=["technician", "status", "updated_at"])
    changed = event(repair, actor, "Technicien affecté", str(technician))
    alert(repair, [repair.client_id, technician.user_id], "Un technicien a été affecté à la réparation", f"{repair.reference} · {repair.pc.name} : {technician} prend en charge votre demande.", f"repair-assigned:{changed.pk}", kind=Notification.Kind.ASSIGNMENT)
    if old_user and old_user != technician.user_id:
        alert(repair, [old_user], "Une réparation a été réaffectée", f"{repair.reference} est désormais confiée à un autre technicien.", f"repair-released:{changed.pk}")
    return repair


def _resolve(repair):
    if not repair.diagnosis.strip() or not repair.solution.strip():
        raise ValidationError("Renseignez le diagnostic et la solution avant de résoudre la demande.")
    pc = PC.objects.select_for_update().get(pk=repair.pc_id)
    now = timezone.now()
    parts = [{"name": line.name_snapshot, "quantity": line.quantity, "unit_price": str(line.unit_price), "total": str(line.total)} for line in repair.component_usages.filter(returned_at__isnull=True)]
    repair.maintenance_record = MaintenanceRecord.objects.create(pc=pc, title=f"{repair.reference} · {repair.get_problem_display()}", kind="repair", description=f"Problème : {repair.description}\n\nDiagnostic : {repair.diagnosis}\n\nSolution : {repair.solution}\n\nPièces : " + (", ".join(f"{p['quantity']} × {p['name']}" for p in parts) or "Aucune"), completed_on=timezone.localdate(now), technician=str(repair.technician))
    total = repair.total_amount.quantize(Decimal("0.001"))
    snapshot = {"repair_id": repair.pk, "reference": repair.reference, "category": "Assistance & Réparation", "scheduled_at": timezone.localtime(repair.created_at).isoformat(), "completed_at": timezone.localtime(now).isoformat(), "client": repair.client.get_full_name() or repair.client.username, "client_email": repair.client.email, "technician": str(repair.technician), "reason": repair.get_problem_display(), "pc": {name: getattr(pc, name) or "" for name in ("name", "brand", "model", "serial_number", "operating_system", "processor", "ram_gb", "storage_gb", "storage_type")}, "diagnosis": repair.diagnosis, "solution": repair.solution, "parts": parts, "parts_total": str(repair.parts_total), "labour_cost": str(repair.labour_cost), "total": str(total), "currency": "TND"}
    Invoice.objects.create(repair=repair, snapshot=snapshot, total_amount=total, issued_at=now)
    repair.closed_at = now


def _transition(repair, actor, status, reason=""):
    if status == repair.status:
        return
    if status not in TRANSITIONS.get(repair.status, []):
        raise ValidationError("Ce changement de statut n’est pas autorisé à cette étape.")
    if status == S.WAITING and not reason.strip():
        raise ValidationError("Indiquez la pièce attendue ou le motif de l’attente.")
    if status == S.RESOLVED:
        _resolve(repair)
    if status == S.CANCELLED:
        from inventory.services import return_target_components
        return_target_components(actor, repair=repair, reason="Annulation de la demande")
        repair.closed_at = timezone.now()
    repair.waiting_reason = reason[:250] if status == S.WAITING else ""
    repair.status = status
    repair.save()
    changed = event(repair, actor, repair.get_status_display(), reason)
    recipients = [repair.client_id]
    if status in (S.CANCELLED, S.WAITING) and repair.technician_id:
        recipients.append(repair.technician.user_id)
    alert(repair, recipients, f"{repair.reference} : {repair.get_status_display().lower()}", f"{repair.pc.name} · {reason or repair.get_problem_display()}", f"repair-status:{changed.pk}", kind=Notification.Kind.COMPONENT if status == S.WAITING else Notification.Kind.STATUS, level="warning" if status in (S.WAITING, S.CANCELLED) else "success" if status == S.RESOLVED else "info")
    if status == S.RESOLVED:
        alert(repair, [repair.client_id], "Votre rapport et votre facture sont disponibles", f"Les documents de {repair.reference} sont prêts dans Rapports & factures.", f"repair-documents:{repair.pk}", kind=Notification.Kind.DOCUMENTS, level="success")


@transaction.atomic
def change_status(actor, repair_id, status, reason=""):
    repair = visible_repairs(actor).select_for_update().select_related("pc", "technician__user", "client").get(pk=repair_id)
    if not can_manage(actor, repair):
        if not (actor.pk == repair.client_id and status == S.CANCELLED and repair.status in (S.SENT, S.ASSIGNED, S.DIAGNOSIS)):
            raise PermissionDenied
    _transition(repair, actor, status, reason)
    return repair


@transaction.atomic
def save_report(actor, repair_id, data, resolve=False):
    repair = visible_repairs(actor).select_for_update().select_related("pc", "technician__user", "client").get(pk=repair_id)
    if not can_manage(actor, repair):
        raise PermissionDenied
    if repair.is_closed or not repair.technician_id or repair.status == S.SENT:
        raise ValidationError("Affectez un technicien et ouvrez le diagnostic avant de renseigner le compte rendu.")
    for name in ("diagnosis", "solution", "labour_cost"):
        setattr(repair, name, data[name])
    repair.full_clean(exclude=["photo"])
    repair.save()
    event(repair, actor, "Compte rendu mis à jour")
    if resolve:
        _transition(repair, actor, S.RESOLVED)
    return repair


@transaction.atomic
def send_message(actor, repair_id, body):
    repair = visible_repairs(actor).select_for_update().get(pk=repair_id)
    if repair.is_closed:
        raise ValidationError("La discussion est en lecture seule après la clôture.")
    body = body.strip()
    if not 1 <= len(body) <= 2000:
        raise ValidationError("Le message doit contenir entre 1 et 2 000 caractères.")
    if not repair.technician_id:
        raise ValidationError("La discussion sera disponible après l’affectation d’un technicien.")
    message = RepairMessage.objects.create(repair=repair, sender=actor, body=body)
    recipients = {repair.client_id, repair.technician.user_id} - {actor.pk}
    alert(repair, recipients, "Vous avez reçu un nouveau message", f"Un nouveau message concerne {repair.reference}.", f"repair-message:{message.pk}", kind=Notification.Kind.MESSAGE)
    return message
