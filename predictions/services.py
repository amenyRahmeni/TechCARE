from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from maintenance.permissions import viewable_pcs
from maintenance.models import PC
from .engine import predict_score, risk_level
from .features import LABELS, display_features, extract_features, fingerprint
from .models import FailureModel, FailurePrediction


def current_model():
    return FailureModel.objects.defer("forest").first()


def context_for_pc(pc):
    model = current_model()
    latest = pc.failure_predictions.select_related("model").defer("model__forest").first()
    values, error = None, ""
    try:
        values = extract_features(pc)
    except ValidationError as exc:
        error = " ".join(exc.messages)
    stale = bool(latest and (not model or latest.model_id != model.pk or not values or latest.input_fingerprint != fingerprint(values)))
    missing, outside = [], []
    if values:
        if values["pc_age_days"] == -1:
            missing.append("Date d’achat non renseignée : l’âge du PC est inconnu.")
        if values["maintenance_count"] == 0:
            missing.append("Aucun entretien enregistré : l’absence d’historique ne prouve pas l’absence de panne.")
        if model:
            for name, bound in model.feature_bounds.items():
                if name in values and not bound["min"] <= values[name] <= bound["max"]:
                    outside.append(LABELS.get(name, name))
    return {"ml_model": model, "prediction": latest, "prediction_stale": stale, "prediction_error": error,
            "prediction_is_demo": latest.model.is_demo if latest else model.is_demo if model else True,
            "feature_rows": display_features(values) if values else [], "missing_features": missing,
            "outside_features": outside, "features": values}


@transaction.atomic
def analyze_pc(actor, pc_id):
    if not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied
    if not viewable_pcs(actor).filter(pk=pc_id).exists():
        raise PermissionDenied
    pc = PC.objects.select_for_update().get(pk=pc_id)
    model = current_model()
    if not model:
        raise ValidationError("Aucun modèle n’est disponible. Demandez à l’administrateur d’entraîner le modèle.")
    values = extract_features(pc)
    score = predict_score(model.forest, values)
    prediction, _ = FailurePrediction.objects.get_or_create(pc=pc, model=model, input_fingerprint=fingerprint(values),
        defaults={"features": values, "score": score, "level": risk_level(score), "created_by": actor})
    return prediction
