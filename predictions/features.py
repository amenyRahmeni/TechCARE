import hashlib
import json

from django.core.exceptions import ValidationError
from django.utils import timezone


# All features are observed at prediction time. The future outcome is never a feature.
FEATURES = (
    "pc_age_days", "ram_gb", "storage_gb", "is_hdd", "is_laptop",
    "maintenance_count", "repair_count", "repairs_last_365d",
    "preventive_last_365d", "days_since_last_maintenance",
)
LABELS = {
    "pc_age_days": "Âge du PC", "ram_gb": "Mémoire RAM", "storage_gb": "Capacité de stockage",
    "is_hdd": "Type de disque", "is_laptop": "Type de PC", "maintenance_count": "Entretiens enregistrés",
    "repair_count": "Réparations enregistrées", "repairs_last_365d": "Réparations sur 12 mois",
    "preventive_last_365d": "Préventions sur 12 mois", "days_since_last_maintenance": "Délai depuis l’entretien",
}
LIMITS = {
    "pc_age_days": (-1, 10958), "ram_gb": (1, 512), "storage_gb": (1, 32768),
    "is_hdd": (0, 1), "is_laptop": (0, 1), "maintenance_count": (0, 10000),
    "repair_count": (0, 10000), "repairs_last_365d": (0, 1000),
    "preventive_last_365d": (0, 1000), "days_since_last_maintenance": (-1, 10958),
}


def validate_features(values):
    if set(values) != set(FEATURES):
        raise ValidationError("Le format des caractéristiques ne correspond pas au modèle.")
    for name in FEATURES:
        value = values[name]
        low, high = LIMITS[name]
        if type(value) is not int or not low <= value <= high:
            raise ValidationError(f"Valeur invalide pour {LABELS[name]} ({low} à {high}).")
    if values["repair_count"] > values["maintenance_count"] or values["repairs_last_365d"] > values["repair_count"]:
        raise ValidationError("Les nombres de réparations sont incohérents.")
    if values["preventive_last_365d"] + values["repairs_last_365d"] > values["maintenance_count"]:
        raise ValidationError("Les entretiens annuels dépassent le total enregistré.")
    if (values["maintenance_count"] == 0) != (values["days_since_last_maintenance"] == -1):
        raise ValidationError("Le délai du dernier entretien est incohérent avec l’historique.")
    if values["maintenance_count"] and values["pc_age_days"] >= 0 and values["days_since_last_maintenance"] > values["pc_age_days"]:
        raise ValidationError("Le dernier entretien ne peut pas précéder l’achat.")
    return values


def extract_features(pc, today=None):
    today = today or timezone.localdate()
    records = list(pc.maintenance_records.filter(completed_on__lte=today).values("kind", "completed_on"))
    recent = [record for record in records if 0 <= (today - record["completed_on"]).days <= 365]
    last = max((record["completed_on"] for record in records), default=None)
    values = {
        "pc_age_days": (today - pc.purchased_on).days if pc.purchased_on else -1,
        "ram_gb": pc.ram_gb, "storage_gb": pc.storage_gb,
        "is_hdd": int(pc.storage_type == "HDD"), "is_laptop": int(pc.device_type == "laptop"),
        "maintenance_count": len(records), "repair_count": sum(record["kind"] == "repair" for record in records),
        "repairs_last_365d": sum(record["kind"] == "repair" for record in recent),
        "preventive_last_365d": sum(record["kind"] == "preventive" for record in recent),
        "days_since_last_maintenance": (today - last).days if last else -1,
    }
    return validate_features(values)


def fingerprint(values, today=None):
    content = {"date": str(today or timezone.localdate()), "features": values, "schema": 1}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def display_features(values):
    def display(name, value):
        if name in ("pc_age_days", "days_since_last_maintenance"):
            return "Non renseigné" if value == -1 else f"{value} jours"
        if name in ("ram_gb", "storage_gb"):
            return f"{value} Go"
        if name == "is_hdd":
            return "HDD" if value else "SSD"
        if name == "is_laptop":
            return "Portable" if value else "Bureau"
        return value
    return [{"label": LABELS[name], "value": display(name, values[name])} for name in FEATURES]
