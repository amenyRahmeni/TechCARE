from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from appointments.models import Technician
from .models import ComponentListing, SparePart, StockMovement

User = get_user_model()


class SeedShowcaseTests(TestCase):
    def prepare_sellers(self):
        call_command("seed_technicians", stdout=StringIO())

    def test_fills_vitrine_without_duplicates_or_overwriting_seller_changes(self):
        self.prepare_sellers()
        accounts = list(User.objects.order_by("pk").values_list("pk", "password", "email", "is_active"))
        call_command("seed_showcase", stdout=StringIO())
        self.assertEqual(ComponentListing.objects.count(), 12)
        self.assertEqual(SparePart.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)
        for name in ("tech_amine", "tech_sarra"):
            self.assertEqual(ComponentListing.objects.filter(seller__user__username=name, status="published").count(), 6)
        for listing in ComponentListing.objects.all():
            self.assertIn("DÉMO", listing.reference)
            self.assertIn("démonstration", listing.description)
            self.assertIn("fictifs", listing.description)
            self.assertTrue(listing.contact_email.endswith("@example.test"))
            self.assertEqual(listing.contact_phone, "")
            listing.full_clean()
        modified = ComponentListing.objects.first()
        modified.title = "Annonce modifiée par le vendeur"
        modified.status = "sold"
        modified.save(update_fields=["title", "status"])
        call_command("seed_showcase", stdout=StringIO())
        modified.refresh_from_db()
        self.assertEqual(ComponentListing.objects.count(), 12)
        self.assertEqual(modified.title, "Annonce modifiée par le vendeur")
        self.assertEqual(modified.status, "sold")
        self.assertEqual(accounts, list(User.objects.order_by("pk").values_list("pk", "password", "email", "is_active")))
        tech = User.objects.get(username="tech_amine")
        self.client.force_login(tech)
        response = self.client.get(reverse("inventory:catalog"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["counts"]["active"], 11)
        self.assertContains(response, "RAM DDR4")
        self.assertContains(response, "DÉMO")

    def test_requires_demo_accounts_and_does_not_create_users(self):
        user = User.objects.create_user("regular_technician", email="real@example.test")
        Technician.objects.create(user=user)
        with self.assertRaises(CommandError):
            call_command("seed_showcase", stdout=StringIO())
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(ComponentListing.objects.count(), 0)

    def test_refuses_to_publish_for_a_demo_account_converted_to_a_real_identity(self):
        self.prepare_sellers()
        User.objects.filter(username="tech_sarra").update(email="sarra@real-business.example")
        with self.assertRaises(CommandError):
            call_command("seed_showcase", stdout=StringIO())
        self.assertEqual(ComponentListing.objects.count(), 0)
