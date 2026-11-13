from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from predictions.dataset import demo_rows, write_csv


class Command(BaseCommand):
    help = "Génère un CSV synthétique reproductible, sans lire ni modifier les PC de MySQL."

    def add_arguments(self, parser):
        parser.add_argument("--output", type=Path, required=True)
        parser.add_argument("--samples", type=int, default=1600)
        parser.add_argument("--seed", type=int, default=42)

    def handle(self, *args, **options):
        try:
            rows = demo_rows(options["samples"], options["seed"])
            output = options["output"]
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8", newline="") as stream:
                write_csv(rows, stream)
        except (OSError, ValidationError) as exc:
            raise CommandError(" ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"{len(rows)} observations simulées enregistrées dans {output}. Aucun historique réel ajouté."))
