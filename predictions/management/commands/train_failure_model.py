from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from predictions.dataset import demo_rows, read_csv
from predictions.training import train_model


class Command(BaseCommand):
    help = "Entraîne une Random Forest sur des données simulées ou un CSV historique, puis active sa version."

    def add_arguments(self, parser):
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument("--demo", action="store_true")
        source.add_argument("--csv", type=Path)
        parser.add_argument("--samples", type=int, default=1600)
        parser.add_argument("--seed", type=int, default=42)

    def handle(self, *args, **options):
        try:
            rows = demo_rows(options["samples"], options["seed"]) if options["demo"] else read_csv(options["csv"].read_bytes())
            model = train_model(rows, seed=options["seed"])
        except (OSError, ValidationError) as exc:
            raise CommandError(" ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Random Forest {model.short_version} : {model.sample_count} observations, {model.train_count} entraînement / {model.test_count} test. {model.get_origin_display()}."))
        self.stdout.write(f"ROC-AUC test : {model.metrics['roc_auc']:.3f}. Ce score évalue le jeu fourni, pas une performance sur d’autres PC.")
