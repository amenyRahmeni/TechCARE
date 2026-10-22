from django.db import transaction
from django.utils import timezone

from .models import MaintenanceRule, PC, Recommendation


def rule_reason(pc, rule, today):
    if rule.criterion == MaintenanceRule.Criterion.RAM and pc.ram_gb < rule.threshold:
        return f"{pc.ram_gb} Go de RAM installés · seuil recommandé : {rule.threshold} Go."
    if rule.criterion == MaintenanceRule.Criterion.STORAGE and pc.storage_gb < rule.threshold:
        return f"{pc.storage_gb} Go de stockage · seuil recommandé : {rule.threshold} Go."
    if rule.criterion == MaintenanceRule.Criterion.HDD and pc.storage_type == PC.StorageType.HDD:
        return "Votre ordinateur utilise un disque dur mécanique (HDD)."
    if rule.criterion == MaintenanceRule.Criterion.OVERDUE:
        baseline = pc.last_maintenance or pc.purchased_on or pc.created_at.date()
        days = (today - baseline).days
        if days >= rule.threshold:
            label = "le dernier entretien" if pc.last_maintenance else "l’achat / l’enregistrement, sans entretien renseigné"
            return f"{days} jours depuis {label} · entretien conseillé tous les {rule.threshold} jours."
    return None


@transaction.atomic
def refresh_recommendations(pc, rules=None):
    rules = list(rules) if rules is not None else list(MaintenanceRule.objects.filter(is_active=True))
    matching_ids = []
    for rule in rules:
        reason = rule_reason(pc, rule, timezone.localdate())
        if reason:
            Recommendation.objects.update_or_create(pc=pc, rule=rule, defaults={"reason": reason, "is_active": True})
            matching_ids.append(rule.pk)
    Recommendation.objects.filter(pc=pc).exclude(rule_id__in=matching_ids).update(is_active=False)


def refresh_all_recommendations(queryset=None):
    rules = list(MaintenanceRule.objects.filter(is_active=True))
    queryset = queryset if queryset is not None else PC.objects.all()
    for pc in queryset.prefetch_related("maintenance_records"):
        refresh_recommendations(pc, rules)
