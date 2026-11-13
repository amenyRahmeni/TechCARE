from collections import Counter
import hashlib
import json

from django.core.exceptions import ValidationError

from .dataset import TARGET
from .engine import predict_score
from .features import FEATURES, LABELS, validate_features
from .learning import ENGINE_VERSION, evaluate, fit_forest, group_split
from .models import FailureModel


def train_model(rows, actor=None, seed=42):
    if not 100 <= len(rows) <= 20000:
        raise ValidationError("L’entraînement exige entre 100 et 20 000 observations.")
    origins = {row["data_origin"] for row in rows}
    if len(origins) != 1 or not origins <= {"simulated", "real"}:
        raise ValidationError("Ne mélangez pas les données simulées et réelles.")
    counts = Counter(row[TARGET] for row in rows)
    if set(counts) != {0, 1} or min(counts.values()) < 20:
        raise ValidationError("Fournissez au moins 20 observations avec panne et 20 sans panne.")
    values = [validate_features({name: row[name] for name in FEATURES}) for row in rows]
    groups = [row["machine_id"] for row in rows]
    if len(set(groups)) < 20:
        raise ValidationError("Le jeu de données doit couvrir au moins 20 machines distinctes.")
    train, test = group_split(rows, TARGET, seed)
    if not train or not test or {rows[i][TARGET] for i in train} != {0, 1} or {rows[i][TARGET] for i in test} != {0, 1}:
        raise ValidationError("La répartition par machine ne permet pas d’évaluer les deux classes. Ajoutez des observations et des machines.")
    train_groups, test_groups = {groups[i] for i in train}, {groups[i] for i in test}
    if train_groups & test_groups:
        raise ValidationError("Une machine ne peut pas appartenir à l’entraînement et au test.")
    parameters = {"n_estimators": 80, "max_depth": 6, "min_samples_leaf": 12, "seed": seed}
    X_train = [[values[index][name] for name in FEATURES] for index in train]
    forest, importance_values = fit_forest(X_train, [rows[index][TARGET] for index in train], **parameters)
    probabilities = [predict_score(forest, values[index]) for index in test]
    baseline = sum(rows[index][TARGET] for index in train) / len(train)
    metrics = {**evaluate([rows[index][TARGET] for index in test], probabilities, baseline),
        "train_machine_count": len(train_groups), "test_machine_count": len(test_groups), "group_overlap_count": 0,
        "train_positive_count": sum(rows[i][TARGET] for i in train), "test_positive_count": sum(rows[i][TARGET] for i in test),
        "seed": seed, "engine_version": ENGINE_VERSION, "horizon_days": 90,
        "split": "Machines distinctes : environ 80 % entraînement / 20 % test", "parameters": parameters}
    importances = sorted([{"feature": name, "label": LABELS[name], "importance": value, "percentage": round(value * 100, 1)} for name, value in zip(FEATURES, importance_values)], key=lambda row: -row["importance"])
    bounds = {name: {"min": min(values[index][name] for index in train), "max": max(values[index][name] for index in train)} for name in FEATURES}
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    return FailureModel.objects.create(origin=next(iter(origins)), dataset_digest=digest, sample_count=len(rows),
        train_count=len(train), test_count=len(test), metrics=metrics, feature_importances=importances,
        feature_bounds=bounds, forest=forest, trained_by=actor)
