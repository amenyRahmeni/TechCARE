"""Bootstrap CART forest with random feature subsets and Gini splits.

Fits labeled examples directly with Python's standard library. PC business rules
are not used to produce a score; each leaf stores its observed class frequency.
"""
from collections import defaultdict
import math
import random

from .features import FEATURES

ENGINE_VERSION = "techcare-random-forest-1"


def fit_forest(X, y, *, seed=42, n_estimators=80, max_depth=6, min_samples_leaf=12):
    rng = random.Random(seed)
    importances = [0.0] * len(FEATURES)
    trees = []

    def impurity(positive, count):
        fraction = positive / count
        return 2 * fraction * (1 - fraction)

    for _ in range(n_estimators):
        tree = {key: [] for key in ("left", "right", "feature", "threshold", "probability")}

        def build(indices, depth):
            count = len(indices)
            positive = sum(y[index] for index in indices)
            node = len(tree["left"])
            for key, value in (("left", -1), ("right", -1), ("feature", -2), ("threshold", 0.0), ("probability", positive / count)):
                tree[key].append(value)
            if depth >= max_depth or count < 2 * min_samples_leaf or positive in (0, count):
                return node
            parent_impurity = impurity(positive, count)
            best_gain, best_feature, best_threshold = 0.0, None, None
            candidates = list(range(len(FEATURES)))
            rng.shuffle(candidates)
            budget = max(1, math.isqrt(len(FEATURES)))
            for examined, feature in enumerate(candidates):
                # Inspect more features if the random subset has no valid split.
                if examined >= budget and best_feature is not None:
                    break
                ordered = sorted(indices, key=lambda index: X[index][feature])
                left_positive = 0
                for position in range(1, count):
                    left_positive += y[ordered[position - 1]]
                    if position < min_samples_leaf or count - position < min_samples_leaf:
                        continue
                    lower, upper = X[ordered[position - 1]][feature], X[ordered[position]][feature]
                    if lower == upper:
                        continue
                    gain = parent_impurity - (position * impurity(left_positive, position) + (count - position) * impurity(positive - left_positive, count - position)) / count
                    if gain > best_gain + 1e-12:
                        best_gain, best_feature, best_threshold = gain, feature, (lower + upper) / 2
            if best_feature is None:
                return node
            left = [index for index in indices if X[index][best_feature] <= best_threshold]
            right = [index for index in indices if X[index][best_feature] > best_threshold]
            importances[best_feature] += count * best_gain
            tree["feature"][node], tree["threshold"][node] = best_feature, best_threshold
            tree["left"][node] = build(left, depth + 1)
            tree["right"][node] = build(right, depth + 1)
            return node

        build([rng.randrange(len(X)) for _ in range(len(X))], 0)
        trees.append(tree)
    total = sum(importances)
    importance = [value / total if total else 0.0 for value in importances]
    return {"schema_version": 1, "features": list(FEATURES), "trees": trees}, importance


def group_split(rows, target, seed=42):
    groups = defaultdict(list)
    for index, row in enumerate(rows):
        groups[row["machine_id"]].append(index)
    strata = defaultdict(list)
    for machine, indices in groups.items():
        majority = int(sum(rows[index][target] for index in indices) >= len(indices) / 2)
        strata[majority].append(machine)
    rng = random.Random(seed)
    test_groups = set()
    for names in strata.values():
        names.sort()
        rng.shuffle(names)
        test_groups.update(names[:max(1, round(len(names) * .2))])
    train = [index for machine, indices in groups.items() if machine not in test_groups for index in indices]
    test = [index for machine, indices in groups.items() if machine in test_groups for index in indices]
    return train, test


def evaluate(targets, scores, baseline):
    predicted = [int(score >= .5) for score in scores]
    matrix = [[0, 0], [0, 0]]
    for target, prediction in zip(targets, predicted):
        matrix[target][prediction] += 1
    tn, fp = matrix[0]
    fn, tp = matrix[1]
    # Pairwise AUC, with half credit for equal-score positive/negative pairs.
    buckets = defaultdict(lambda: [0, 0])
    for target, score in zip(targets, scores):
        buckets[score][target] += 1
    negative_before = 0
    wins = 0.0
    for score in sorted(buckets):
        negative, positive = buckets[score]
        wins += positive * (negative_before + .5 * negative)
        negative_before += negative
    return {
        "accuracy": (tn + tp) / len(targets),
        "balanced_accuracy": .5 * (tn / (tn + fp) + tp / (tp + fn)),
        "roc_auc": wins / ((tp + fn) * (tn + fp)),
        "brier_score": sum((target - score) ** 2 for target, score in zip(targets, scores)) / len(targets),
        "baseline_brier_score": sum((target - baseline) ** 2 for target in targets) / len(targets),
        "confusion_matrix": matrix,
    }
