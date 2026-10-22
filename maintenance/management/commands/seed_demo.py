from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from maintenance.models import MaintenanceRecord, PC
from maintenance.services import refresh_all_recommendations


class Command(BaseCommand):
    help = "Crée un client et des PC de démonstration locaux, sans écraser les données existantes."

    def add_arguments(self, parser):
        parser.add_argument("--with-admin", action="store_true", help="Crée également un administrateur de démonstration local.")

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        today = timezone.localdate()
        client, created = User.objects.get_or_create(username="demo", defaults={"first_name": "Client", "last_name": "Démo", "email": "demo@example.test"})
        if created:
            client.set_password("AtelierPC2026!")
            client.save()
        examples = [
            {"serial_number": "DEMO-DELL-001", "name": "Mon PC de travail", "brand": "Dell", "model": "Latitude 5420", "operating_system": "Windows 11", "processor": "Intel Core i5-1145G7", "ram_gb": 16, "storage_gb": 512, "storage_type": "SSD", "purchased_on": today - timedelta(days=900)},
            {"serial_number": "DEMO-ASUS-002", "name": "Mon PC personnel", "brand": "Asus", "model": "VivoBook 15", "operating_system": "Windows 10", "processor": "Intel Core i3-1005G1", "ram_gb": 4, "storage_gb": 1000, "storage_type": "HDD", "purchased_on": today - timedelta(days=720), "notes": "Utilisé pour la bureautique et les cours. Un peu lent au démarrage."},
            {"serial_number": "DEMO-LENOVO-003", "name": "Le PC du bureau", "brand": "Lenovo", "model": "ThinkCentre M70s", "device_type": "desktop", "operating_system": "Ubuntu", "processor": "Intel Core i5-10400", "ram_gb": 8, "storage_gb": 256, "storage_type": "SSD", "purchased_on": today - timedelta(days=400)},
        ]
        pcs = []
        for values in examples:
            data = values.copy()
            serial = data.pop("serial_number")
            pc, _ = PC.objects.get_or_create(owner=client, serial_number=serial, defaults=data)
            pcs.append(pc)
        records = [
            (pcs[0], "Nettoyage et entretien préventif", "preventive", 45, "Dépoussiérage des ventilateurs et des grilles d’aération. Vérification des températures et du bon fonctionnement général.", "Amine Trabelsi"),
            (pcs[0], "Mise à niveau de la mémoire RAM", "upgrade", 190, "Installation de 16 Go de mémoire RAM et test de stabilité.", "Amine Trabelsi"),
            (pcs[1], "Diagnostic et entretien général", "preventive", 240, "Nettoyage des grilles d’aération et vérification du disque dur. Un remplacement par un SSD est conseillé pour améliorer la réactivité.", "Sarra Mansour"),
            (pcs[2], "Vérification du système et nettoyage", "preventive", 30, "Nettoyage interne, vérification des connexions et contrôle des mises à jour du système.", "Sarra Mansour"),
        ]
        for pc, title, kind, days, description, technician in records:
            MaintenanceRecord.objects.get_or_create(pc=pc, title=title, defaults={"kind": kind, "completed_on": today - timedelta(days=days), "description": description, "technician": technician})
        if options["with_admin"]:
            admin, created = User.objects.get_or_create(username="admin_demo", defaults={"is_staff": True, "is_superuser": True, "first_name": "Admin", "last_name": "Démo"})
            if created:
                admin.set_password("AdminAtelier2026!")
                admin.save()
            self.stdout.write("Administrateur de démo : admin_demo (mot de passe initial dans le README).")
        refresh_all_recommendations(client.pcs.all())
        self.stdout.write(self.style.SUCCESS("Démonstration prête : compte demo, 3 PC et leur historique. Les données existantes ont été conservées."))
