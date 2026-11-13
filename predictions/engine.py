from django.core.exceptions import ValidationError

from .features import FEATURES, validate_features


def predict_score(forest, values):
    validate_features(values)
    if forest.get("schema_version") != 1 or forest.get("features") != list(FEATURES) or not forest.get("trees"):
        raise ValidationError("Ce modèle n’est pas compatible. Réentraînez le modèle.")
    vector = [values[name] for name in FEATURES]
    scores = []
    for tree in forest["trees"]:
        node = 0
        while tree["left"][node] != -1:
            node = tree["left"][node] if vector[tree["feature"][node]] <= tree["threshold"][node] else tree["right"][node]
        scores.append(tree["probability"][node])
    return sum(scores) / len(scores)


def risk_level(score):
    if not 0 <= score <= 1:
        raise ValidationError("Score invalide.")
    return "low" if score < .25 else "medium" if score < .60 else "high"
