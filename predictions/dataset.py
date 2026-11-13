import csv
from datetime import date, timedelta
from io import StringIO
import math
import random

from django.core.exceptions import ValidationError
from django.utils import timezone

from .features import FEATURES, validate_features

TARGET = "failure_within_90d"
HEADERS = ("data_origin", "machine_id", "observed_on", *FEATURES, TARGET)
MAX_ROWS = 20000


def demo_rows(samples=1600, seed=42):
    if not 100 <= samples <= MAX_ROWS:
        raise ValidationError(f"Choisissez entre 100 et {MAX_ROWS} observations.")
    rng = random.Random(seed)
    rows = []
    for index in range(samples):
        actual_age = rng.randint(90, 3650)
        count = rng.randint(0, min(16, actual_age // 90))
        repairs = rng.randint(0, count)
        last = rng.randint(0, actual_age) if count else -1
        recent_repairs = rng.randint(0, min(repairs, 4)) if last != -1 and last <= 365 else 0
        preventive = rng.randint(0, min(count - repairs, 3)) if last != -1 and last <= 365 else 0
        features = {
            "pc_age_days": actual_age if rng.random() > .12 else -1,
            "ram_gb": rng.choice([4, 8, 16, 32, 64]), "storage_gb": rng.choice([128, 256, 512, 1024, 2048]),
            "is_hdd": int(rng.random() < .38), "is_laptop": int(rng.random() < .7),
            "maintenance_count": count, "repair_count": repairs, "repairs_last_365d": recent_repairs,
            "preventive_last_365d": preventive, "days_since_last_maintenance": last,
        }
        # A synthetic stochastic process, NOT an empirical law of PC failures.
        latent = (-3.2 + actual_age / 1500 + .65 * features["is_hdd"]
                  + .6 * recent_repairs - .6 * preventive
                  + min(last if last >= 0 else actual_age, 1600) / 1800)
        probability = 1 / (1 + math.exp(-latent))
        rows.append({"data_origin": "simulated", "machine_id": f"demo-{index:05d}", "observed_on": "2025-01-01",
                     **features, TARGET: int(rng.random() < probability)})
    return rows


def write_csv(rows, stream):
    writer = csv.DictWriter(stream, fieldnames=HEADERS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


def read_csv(content):
    if len(content) > 5 * 1024 * 1024:
        raise ValidationError("Le CSV doit faire au maximum 5 Mo.")
    try:
        text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
        reader = csv.DictReader(StringIO(text))
        if reader.fieldnames is None or len(reader.fieldnames) != len(HEADERS) or set(reader.fieldnames) != set(HEADERS):
            raise ValidationError("Colonnes CSV incorrectes. Utilisez le gabarit fourni.")
        rows = []
        seen = set()
        for line, source in enumerate(reader, 2):
            if len(rows) >= MAX_ROWS:
                raise ValidationError(f"Le CSV est limité à {MAX_ROWS} observations.")
            if None in source or any(value is None for value in source.values()):
                raise ValidationError(f"Ligne {line} : colonnes manquantes ou supplémentaires.")
            origin = source["data_origin"].strip()
            machine = source["machine_id"].strip()
            observed = date.fromisoformat(source["observed_on"].strip())
            if origin not in ("simulated", "real") or not machine or len(machine) > 80:
                raise ValidationError(f"Ligne {line} : origine ou identifiant de machine invalide.")
            if origin == "real" and (machine.startswith("demo-") or observed > timezone.localdate() - timedelta(days=90)):
                raise ValidationError(f"Ligne {line} : un historique réel exige un suivi complet de 90 jours, sans machine de démonstration.")
            key = (machine, observed.isoformat())
            if key in seen:
                raise ValidationError(f"Ligne {line} : observation dupliquée pour cette machine et cette date.")
            seen.add(key)
            features = validate_features({name: int(source[name]) for name in FEATURES})
            target = int(source[TARGET])
            if target not in (0, 1):
                raise ValidationError(f"Ligne {line} : la panne observée doit valoir 0 ou 1.")
            rows.append({"data_origin": origin, "machine_id": machine, "observed_on": observed.isoformat(), **features, TARGET: target})
    except (UnicodeError, ValueError, csv.Error, OverflowError) as error:
        raise ValidationError("CSV invalide : utilisez UTF-8, des dates AAAA-MM-JJ et des nombres entiers.") from error
    if not rows or len({row["data_origin"] for row in rows}) != 1:
        raise ValidationError("Le CSV doit contenir une seule origine : simulated ou real.")
    return rows
