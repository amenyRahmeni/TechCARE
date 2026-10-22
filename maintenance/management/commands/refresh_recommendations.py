from django.core.management.base import BaseCommand
from maintenance.services import refresh_all_recommendations


class Command(BaseCommand):
    help = "Actualise les recommandations de tous les PC (à planifier quotidiennement si nécessaire)."

    def handle(self, *args, **options):
        refresh_all_recommendations()
        self.stdout.write(self.style.SUCCESS("Recommandations actualisées."))
