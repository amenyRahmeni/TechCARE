from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from appointments.models import Technician


class Command(BaseCommand):
    help = "Ajoute deux techniciens de démonstration sans modifier les comptes existants."

    @transaction.atomic
    def handle(self, *args, **options):
        for username, first, last, specialty in [("tech_amine", "Amine", "Trabelsi", "Matériel, entretien et mise à niveau"), ("tech_sarra", "Sarra", "Mansour", "Diagnostic et assistance logicielle")]:
            user, created = get_user_model().objects.get_or_create(username=username, defaults={"first_name": first, "last_name": last, "email": f"{username}@example.test"})
            if created:
                user.set_password("Technicien2026!")
                user.save()
                Technician.objects.create(user=user, specialty=specialty)
            elif not Technician.objects.filter(user=user).exists():
                self.stdout.write(self.style.WARNING(f"Compte {username} déjà existant sans rôle technicien : laissé intact. Affectez son rôle dans l’administration si nécessaire."))
        self.stdout.write(self.style.SUCCESS("Techniciens de démonstration prêts : tech_amine et tech_sarra. Mot de passe initial dans le README."))
