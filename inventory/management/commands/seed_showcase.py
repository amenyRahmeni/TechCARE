from decimal import Decimal
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from appointments.models import Technician
from inventory.demo_showcase import DEMO_LISTINGS, DEMO_NOTICE, DEMO_SELLERS
from inventory.listing_services import save_listing
from inventory.models import Category, ComponentListing


class Command(BaseCommand):
    help = "Ajoute 12 annonces fictives aux deux comptes techniciens de démonstration, sans modifier les annonces existantes."

    @transaction.atomic
    def handle(self, *args, **options):
        sellers = {tech.user.username: tech for tech in Technician.objects.filter(user__username__in=DEMO_SELLERS, user__is_active=True, user__is_staff=False).select_related("user")}
        if set(sellers) != set(DEMO_SELLERS) or any(tech.user.email.lower() != f"{name}@example.test" for name, tech in sellers.items()):
            raise CommandError("Les comptes techniciens de démonstration tech_amine et tech_sarra doivent être actifs avec leurs e-mails @example.test. Aucun compte n’a été modifié. Préparez-les avec seed_technicians si nécessaire.")
        categories = {category.code: category for category in Category.objects.all()}
        missing = {item["category"] for item in DEMO_LISTINGS} - categories.keys()
        if missing:
            raise CommandError("Catégories manquantes : " + ", ".join(sorted(missing)) + ". Appliquez les migrations avant de relancer.")
        created, preserved = 0, 0
        for item in DEMO_LISTINGS:
            token = uuid.uuid5(uuid.NAMESPACE_URL, "techcare:demo-showcase:v1:" + item["key"])
            if ComponentListing.objects.filter(submission_token=token).exists():
                preserved += 1
                continue
            seller = sellers[item["seller"]]
            save_listing(seller.user, {
                "submission_token": token, "title": item["title"], "category": categories[item["category"]],
                "brand": "Générique", "reference": item["reference"], "condition": item["condition"],
                "unit_price": Decimal(item["price"]), "quantity": item["quantity"],
                "description": DEMO_NOTICE + "\n\n" + item["description"],
                "compatibility_notes": item["compatibility"], "location": item["location"],
                "contact_phone": "", "contact_email": seller.user.email,
            })
            created += 1
        self.stdout.write(self.style.SUCCESS(f"Vitrine : {created} annonce(s) de démonstration ajoutée(s), {preserved} annonce(s) existante(s) conservée(s). Prix et quantités fictifs en TND ; stock de l’atelier inchangé."))
