from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from appointments.models import Technician
from repairs.tests import photo_upload
from .listing_forms import ListingForm
from .listing_services import change_listing_status, save_listing
from .models import Category, ComponentListing, SparePart, StockMovement


class ShowcaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.seller = User.objects.create_user("seller_amine", first_name="Amine", last_name="Trabelsi", email="private-account@example.test")
        cls.buyer = User.objects.create_user("buyer_sarra", first_name="Sarra", last_name="Mansour")
        cls.customer = User.objects.create_user("ordinary_customer")
        cls.admin = User.objects.create_user("showcase_admin", is_staff=True)
        cls.vendor = Technician.objects.create(user=cls.seller, specialty="Matériel")
        cls.other_vendor = Technician.objects.create(user=cls.buyer, specialty="Logiciel")
        cls.category = Category.objects.get(code="ram")

    def data(self, **changes):
        data = {"title": "Barrette DDR4 8 Go disponible", "category": self.category, "brand": "Crucial", "reference": "CT8G4S", "condition": "used", "unit_price": Decimal("45.125"), "quantity": 2, "description": "Mémoire testée et fonctionnelle.", "compatibility_notes": "DDR4 SO-DIMM pour portable compatible.", "location": "Tunis, Centre-ville", "contact_phone": "+216 22 123 456", "contact_email": "", "photo": None, "submission_token": uuid.uuid4()}
        data.update(changes)
        return data

    def listing(self, **changes):
        return save_listing(self.seller, self.data(**changes))

    def payload(self, **changes):
        data = self.data()
        data["category"] = self.category.pk
        data.pop("photo")
        data["action"] = "publish"
        data.update(changes)
        return data

    def test_only_technicians_and_staff_can_browse_component_routes(self):
        listing = self.listing()
        paths = [reverse("inventory:catalog"), reverse("inventory:my_listings"), reverse("inventory:listing_create"), listing.get_absolute_url(), reverse("inventory:listing_photo", args=[listing.pk]), reverse("inventory:stock_catalog")]
        self.client.force_login(self.customer)
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 403, path)
        home = self.client.get("/")
        self.assertNotContains(home, 'href="/composants/"')
        self.assertNotContains(home, "Mes annonces")
        self.client.logout()
        self.assertEqual(self.client.get(reverse("inventory:catalog")).status_code, 302)

    def test_a_technician_can_publish_without_affecting_workshop_stock(self):
        self.client.force_login(self.seller)
        self.assertEqual(self.client.get(reverse("inventory:listing_create")).status_code, 200)
        response = self.client.post(reverse("inventory:listing_create"), self.payload(seller=self.other_vendor.pk))
        self.assertEqual(response.status_code, 302)
        listing = ComponentListing.objects.get()
        self.assertEqual(listing.seller_id, self.vendor.pk)
        self.assertEqual(listing.status, "published")
        self.assertEqual(listing.unit_price, Decimal("45.125"))
        self.assertFalse(SparePart.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_showcase_and_details_identify_seller_and_provided_contact(self):
        listing = self.listing()
        self.client.force_login(self.buyer)
        page = self.client.get(reverse("inventory:catalog"))
        for text in [listing.title, "Proposé par", "Amine Trabelsi", "Tunis, Centre-ville"]:
            self.assertContains(page, text)
        detail = self.client.get(listing.get_absolute_url())
        self.assertContains(detail, 'href="tel:+21622123456"')
        self.assertContains(detail, "+216 22 123 456")
        self.assertNotContains(detail, self.seller.email)
        self.assertNotContains(detail, "Modifier l’annonce")

    def test_regular_technician_can_publish_and_see_other_sellers(self):
        self.listing()
        other = save_listing(self.buyer, self.data(title="SSD proposé par Sarra", contact_phone="", contact_email="sarra-sales@example.test", location="Sousse"))
        self.client.force_login(self.seller)
        response = self.client.get(reverse("inventory:catalog"))
        self.assertContains(response, "SSD proposé par Sarra")
        self.assertContains(response, "Sarra Mansour")
        self.assertContains(self.client.get(other.get_absolute_url()), 'href="mailto:sarra-sales@example.test"')

    def test_other_technicians_cannot_edit_or_change_status(self):
        listing = self.listing()
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.get(reverse("inventory:listing_update", args=[listing.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("inventory:listing_update", args=[listing.pk]), self.payload(title="Hijacked")).status_code, 403)
        self.assertEqual(self.client.post(reverse("inventory:listing_status", args=[listing.pk]), {"status": "sold"}).status_code, 403)
        listing.refresh_from_db()
        self.assertEqual(listing.status, "published")
        self.assertEqual(listing.seller_id, self.vendor.pk)

    def test_owner_can_edit_price_quantity_and_contact_without_transferring_ownership(self):
        listing = self.listing()
        self.client.force_login(self.seller)
        response = self.client.post(reverse("inventory:listing_update", args=[listing.pk]), self.payload(title="RAM mise à jour", unit_price="39.900", quantity=3, seller=self.other_vendor.pk))
        self.assertEqual(response.status_code, 302)
        listing.refresh_from_db()
        self.assertEqual((listing.title, listing.quantity, listing.unit_price), ("RAM mise à jour", 3, Decimal("39.900")))
        self.assertEqual(listing.seller_id, self.vendor.pk)

    def test_drafts_are_only_visible_to_owner_and_staff(self):
        listing = save_listing(self.seller, self.data(), draft=True)
        self.client.force_login(self.buyer)
        self.assertNotContains(self.client.get(reverse("inventory:catalog")), listing.title)
        self.assertEqual(self.client.get(listing.get_absolute_url()).status_code, 404)
        self.client.force_login(self.seller)
        self.assertContains(self.client.get(reverse("inventory:my_listings")), listing.title)
        self.assertEqual(self.client.get(listing.get_absolute_url()).status_code, 200)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(listing.get_absolute_url()).status_code, 200)

    def test_owner_can_mark_sold_withdraw_and_republish(self):
        listing = self.listing()
        for status in ("sold", "withdrawn", "published"):
            self.client.force_login(self.seller)
            self.client.post(reverse("inventory:listing_status", args=[listing.pk]), {"status": status})
            listing.refresh_from_db()
            self.assertEqual(listing.status, status)
            self.assertContains(self.client.get(reverse("inventory:my_listings")), listing.title)
            self.client.force_login(self.buyer)
            self.assertEqual(self.client.get(listing.get_absolute_url()).status_code, 200 if status == "published" else 404)

    def test_invalid_state_and_inactive_seller_do_not_publish(self):
        listing = self.listing()
        with self.assertRaises(ValidationError):
            change_listing_status(self.seller, listing.pk, "unknown")
        self.seller.is_active = False
        self.seller.save()
        self.client.force_login(self.buyer)
        self.assertNotContains(self.client.get(reverse("inventory:catalog")), listing.title)
        self.assertEqual(self.client.get(listing.get_absolute_url()).status_code, 404)
        with self.assertRaises(ValidationError):
            change_listing_status(self.admin, listing.pk, "published")

    def test_work_availability_does_not_hide_a_sellers_announcements(self):
        listing = self.listing()
        self.vendor.is_available = False
        self.vendor.save()
        self.client.force_login(self.buyer)
        self.assertContains(self.client.get(reverse("inventory:catalog")), listing.title)

    def test_filters_search_seller_category_prices_and_my_listings(self):
        listing = self.listing()
        other = save_listing(self.buyer, self.data(title="RAM vendue par Sarra", unit_price=Decimal("80.000"), location="Sousse"))
        self.client.force_login(self.buyer)
        url = reverse("inventory:catalog")
        self.assertContains(self.client.get(url + f"?seller={self.vendor.pk}&category=ram&min_price=40&max_price=50"), listing.title)
        self.assertNotContains(self.client.get(url + f"?seller={self.vendor.pk}"), other.title)
        self.assertContains(self.client.get(url + "?q=Amine"), listing.title)
        self.assertContains(self.client.get(url + "?q=Tunis"), listing.title)
        self.assertNotContains(self.client.get(url + "?q=Tunis"), other.title)
        self.assertNotContains(self.client.get(reverse("inventory:my_listings")), listing.title)
        self.assertContains(self.client.get(reverse("inventory:my_listings")), other.title)
        self.assertContains(self.client.get(url + "?min_price=NaN"), "prix positif valide")

    def test_contacts_price_and_quantity_are_validated(self):
        for changes in [{"contact_phone": "", "contact_email": ""}, {"contact_phone": "javascript:alert(1)"}, {"contact_phone": "1------"}, {"contact_email": "invalid"}, {"unit_price": "-1"}, {"quantity": "0"}]:
            form = ListingForm(self.payload(**changes))
            self.assertFalse(form.is_valid(), changes)
        self.assertEqual(ComponentListing.objects.count(), 0)

    def test_submission_is_idempotent_and_token_cannot_be_reused_by_another_vendor(self):
        data = self.data()
        first = save_listing(self.seller, data)
        second = save_listing(self.seller, data)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ComponentListing.objects.count(), 1)
        with self.assertRaises(PermissionDenied):
            save_listing(self.buyer, data)

    def test_photo_is_reencoded_named_randomly_and_private_to_technicians(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            form = ListingForm(self.payload(), {"photo": photo_upload()})
            self.assertTrue(form.is_valid(), form.errors)
            listing = save_listing(self.seller, form.cleaned_data)
            self.assertRegex(listing.photo.name, r"^component-listings/[a-f0-9]{32}\.jpg$")
            with Image.open(listing.photo.path) as image:
                self.assertEqual(image.format, "JPEG")
                self.assertFalse(image.getexif())
            self.client.force_login(self.buyer)
            response = self.client.get(reverse("inventory:listing_photo", args=[listing.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertIn("no-store", response["Cache-Control"])
            self.assertTrue(b"".join(response.streaming_content).startswith(b"\xff\xd8"))
            change_listing_status(self.seller, listing.pk, "withdrawn")
            self.assertEqual(self.client.get(reverse("inventory:listing_photo", args=[listing.pk])).status_code, 404)
            self.client.force_login(self.customer)
            self.assertEqual(self.client.get(reverse("inventory:listing_photo", args=[listing.pk])).status_code, 403)

    def test_invalid_images_do_not_create_announcements(self):
        form = ListingForm(self.payload(), {"photo": SimpleUploadedFile("fake.svg", b"<svg></svg>", content_type="image/svg+xml")})
        self.assertFalse(form.is_valid())
        self.assertIn("photo", form.errors)

    def test_failed_save_cleans_new_photo_and_preserves_previous_photo(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            form = ListingForm(self.payload(), {"photo": photo_upload()})
            self.assertTrue(form.is_valid())
            listing = save_listing(self.seller, form.cleaned_data)
            original_name = listing.photo.name
            update = ListingForm(self.payload(title="Nouvelle photo"), {"photo": photo_upload()}, instance=listing)
            self.assertTrue(update.is_valid(), update.errors)
            with patch.object(ComponentListing, "save", side_effect=RuntimeError("Simulated failure")), self.assertRaises(RuntimeError):
                save_listing(self.seller, update.cleaned_data, pk=listing.pk)
            listing.refresh_from_db()
            self.assertEqual(listing.photo.name, original_name)
            self.assertEqual(len(list(Path(directory).rglob("*.jpg"))), 1)

    def test_photo_replacement_and_removal_happen_after_commit(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            create = ListingForm(self.payload(), {"photo": photo_upload()})
            self.assertTrue(create.is_valid())
            listing = save_listing(self.seller, create.cleaned_data)
            old_path = Path(listing.photo.path)
            update = ListingForm(self.payload(), {"photo": photo_upload()}, instance=listing)
            self.assertTrue(update.is_valid(), update.errors)
            with self.captureOnCommitCallbacks(execute=True):
                listing = save_listing(self.seller, update.cleaned_data, pk=listing.pk)
            self.assertFalse(old_path.exists())
            current_path = Path(listing.photo.path)
            remove = ListingForm(self.payload(remove_photo="on"), instance=listing)
            self.assertTrue(remove.is_valid(), remove.errors)
            with self.captureOnCommitCallbacks(execute=True):
                listing = save_listing(self.seller, remove.cleaned_data, pk=listing.pk)
            self.assertFalse(current_path.exists())
            self.assertFalse(listing.photo)

    def test_mutations_require_csrf_and_status_get_is_rejected(self):
        listing = self.listing()
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.seller)
        self.assertEqual(secure.post(reverse("inventory:listing_status", args=[listing.pk]), {"status": "sold"}).status_code, 403)
        self.client.force_login(self.seller)
        self.assertEqual(self.client.get(reverse("inventory:listing_status", args=[listing.pk])).status_code, 405)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("inventory:catalog")).status_code, 200)
        self.assertEqual(self.client.get(reverse("inventory:listing_create")).status_code, 403)

    def test_untrusted_advertisement_text_is_escaped(self):
        listing = self.listing(title='<script>alert("x")</script>')
        self.client.force_login(self.buyer)
        response = self.client.get(listing.get_absolute_url())
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("x")</script>')

    def test_technician_role_is_preserved_when_the_profile_has_announcements(self):
        from backoffice.forms import AccountForm
        self.listing()
        form = AccountForm({"username": self.seller.username, "first_name": "Amine", "last_name": "Trabelsi", "email": self.seller.email, "role": "client"}, actor=self.admin, instance=self.seller)
        self.assertFalse(form.is_valid())
        self.assertIn("annonces", str(form.errors["role"]))
