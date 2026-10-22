from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import MaintenanceRecord, MaintenanceRule, PC, Recommendation
from .services import refresh_recommendations


class MaintenanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(username="client", password="TestOnly2026!")
        cls.other = get_user_model().objects.create_user(username="other", password="TestOnly2026!")

    def setUp(self):
        self.client.force_login(self.owner)
        self.today = timezone.localdate()
        self.pc = PC.objects.create(owner=self.owner, name="PC principal", brand="Dell", model="Latitude", serial_number="SER-1", operating_system="Ubuntu", ram_gb=16, storage_gb=512, storage_type="SSD", purchased_on=self.today - timedelta(days=30))

    def payload(self, **changes):
        data = {"name": "Nouveau PC", "brand": "HP", "model": "ProBook", "device_type": "laptop", "operating_system": "Windows 11", "ram_gb": 8, "storage_gb": 512, "storage_type": "SSD", "serial_number": "SER-2"}
        data.update(changes)
        return data

    def record(self, days=10, **changes):
        data = {"pc": self.pc, "title": "Nettoyage", "description": "Ventilateurs nettoyés.", "completed_on": self.today - timedelta(days=days)}
        data.update(changes)
        return MaintenanceRecord.objects.create(**data)

    def test_anonymous_pages_require_login(self):
        self.client.logout()
        for url in ["/", "/historique/", "/recommandations/", "/pc/ajouter/", self.pc.get_absolute_url()]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)

    def test_all_client_templates_render(self):
        self.record()
        for url in ["/", "/historique/", "/recommandations/", "/pc/ajouter/", self.pc.get_absolute_url(), f"/pc/{self.pc.pk}/modifier/", f"/pc/{self.pc.pk}/supprimer/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_pc_create_assigns_current_user_and_ignores_owner_injection(self):
        response = self.client.post(reverse("maintenance:pc_create"), self.payload(owner=self.other.pk))
        pc = PC.objects.get(serial_number="SER-2")
        self.assertEqual(pc.owner, self.owner)
        self.assertRedirects(response, pc.get_absolute_url())

    def test_pc_update_recomputes_recommendations(self):
        self.client.post(reverse("maintenance:pc_update", args=[self.pc.pk]), self.payload(serial_number="SER-1", ram_gb=4))
        self.assertTrue(Recommendation.objects.filter(pc=self.pc, rule__code="ram-upgrade", is_active=True).exists())
        self.client.post(reverse("maintenance:pc_update", args=[self.pc.pk]), self.payload(serial_number="SER-1", ram_gb=16))
        self.assertFalse(Recommendation.objects.filter(pc=self.pc, rule__code="ram-upgrade", is_active=True).exists())

    def test_other_client_cannot_view_edit_delete_or_see_history(self):
        self.record()
        self.client.force_login(self.other)
        for route in ("pc_detail", "pc_update", "pc_delete"):
            url = reverse(f"maintenance:{route}", args=[self.pc.pk])
            with self.subTest(route=route):
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url, self.payload()).status_code, 404)
        self.assertNotContains(self.client.get("/"), self.pc.name)
        self.assertNotContains(self.client.get(f"/historique/?pc={self.pc.pk}"), "Ventilateurs nettoyés.")

    def test_delete_get_is_confirmation_and_post_cascades(self):
        self.record()
        self.pc.ram_gb = 4
        self.pc.save()
        url = reverse("maintenance:pc_delete", args=[self.pc.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(PC.objects.filter(pk=self.pc.pk).exists())
        self.assertRedirects(self.client.post(url), "/")
        self.assertFalse(PC.objects.filter(pk=self.pc.pk).exists())
        self.assertFalse(MaintenanceRecord.objects.exists())
        self.assertFalse(Recommendation.objects.exists())

    def test_duplicate_serial_is_rejected_for_same_owner(self):
        response = self.client.post("/pc/ajouter/", self.payload(serial_number="SER-1"))
        self.assertContains(response, "Vous avez déjà un PC avec ce numéro de série.")
        self.assertEqual(self.owner.pcs.count(), 1)

    def test_other_owner_can_use_same_serial_and_blank_serials_can_repeat(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.post("/pc/ajouter/", self.payload(serial_number="SER-1")).status_code, 302)
        for _ in range(2):
            self.assertEqual(self.client.post("/pc/ajouter/", self.payload(serial_number="")).status_code, 302)

    def test_mysql_enforces_serial_uniqueness_without_form_validation(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PC.objects.create(owner=self.owner, **self.payload(serial_number="SER-1"))

    def test_empty_serial_is_null_and_can_repeat_in_mysql(self):
        for serial in ("", "   ", None):
            pc = PC.objects.create(owner=self.owner, **self.payload(serial_number=serial))
            pc.refresh_from_db()
            self.assertIsNone(pc.serial_number)

    def test_serial_comparison_remains_case_sensitive(self):
        pc = PC.objects.create(owner=self.owner, **self.payload(serial_number="ser-1"))
        self.assertNotEqual(pc.pk, self.pc.pk)
        self.assertEqual(self.owner.pcs.filter(serial_number="SER-1").count(), 1)

    def test_mysql_preserves_french_arabic_and_emoji(self):
        self.pc.name = "PC étudiant 🖥️"
        self.pc.notes = "حاسوب للصيانة — mémoire vérifiée ✅"
        self.pc.save()
        saved = PC.objects.get(pk=self.pc.pk)
        self.assertEqual(saved.name, self.pc.name)
        self.assertEqual(saved.notes, self.pc.notes)

    def test_invalid_numeric_values_future_dates_and_empty_name(self):
        for changes in ({"ram_gb": 0}, {"ram_gb": 513}, {"storage_gb": -1}, {"storage_gb": 32769}, {"purchased_on": self.today + timedelta(days=1)}, {"name": "   "}):
            with self.subTest(changes=changes):
                response = self.client.post("/pc/ajouter/", self.payload(**changes))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        self.assertEqual(self.owner.pcs.count(), 1)

    def test_purchase_date_cannot_move_after_existing_history(self):
        self.record(days=20)
        response = self.client.post(reverse("maintenance:pc_update", args=[self.pc.pk]), self.payload(serial_number="SER-1", purchased_on=self.today - timedelta(days=5)))
        self.assertIn("purchased_on", response.context["form"].errors)

    def test_maintenance_date_validation(self):
        for date in (self.today + timedelta(days=1), self.today - timedelta(days=100)):
            record = MaintenanceRecord(pc=self.pc, title="Test", description="Test", completed_on=date)
            with self.assertRaises(ValidationError):
                record.full_clean()

    def test_overdue_rule_boundary_and_latest_maintenance(self):
        self.pc.purchased_on = self.today - timedelta(days=180)
        self.pc.save()
        self.assertTrue(self.pc.recommendations.filter(rule__code="preventive-cleaning", is_active=True).exists())
        self.record(days=20)
        self.record(days=100, title="Ancien entretien")
        self.assertEqual(self.pc.last_maintenance, self.today - timedelta(days=20))
        self.assertFalse(self.pc.recommendations.filter(rule__code="preventive-cleaning", is_active=True).exists())

    def test_deleting_latest_maintenance_reactivates_overdue_rule(self):
        self.pc.purchased_on = self.today - timedelta(days=400)
        self.pc.save()
        record = self.record()
        self.assertFalse(self.pc.recommendations.filter(rule__code="preventive-cleaning", is_active=True).exists())
        record.delete()
        self.assertTrue(self.pc.recommendations.filter(rule__code="preventive-cleaning", is_active=True).exists())

    def test_rule_changes_are_parameterized_and_recalculate_existing_pcs(self):
        rule = MaintenanceRule.objects.get(code="ram-upgrade")
        rule.threshold = 32
        rule.save()
        self.assertTrue(self.pc.recommendations.filter(rule=rule, is_active=True).exists())
        rule.is_active = False
        rule.save()
        self.assertFalse(self.pc.recommendations.filter(rule=rule, is_active=True).exists())

    def test_repeated_analysis_does_not_duplicate_recommendations(self):
        self.pc.ram_gb = 4
        self.pc.storage_type = "HDD"
        self.pc.save()
        for _ in range(3):
            refresh_recommendations(self.pc)
        self.assertEqual(self.pc.recommendations.filter(is_active=True).count(), 2)

    def test_analyze_is_post_only_and_limited_to_current_user(self):
        self.assertEqual(self.client.get(reverse("maintenance:analyze")).status_code, 405)
        self.client.force_login(self.other)
        self.pc.ram_gb = 4
        PC.objects.filter(pk=self.pc.pk).update(ram_gb=4)
        self.client.post(reverse("maintenance:analyze"))
        self.assertFalse(self.pc.recommendations.filter(is_active=True).exists())

    def test_mutations_require_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        for url in ("/pc/ajouter/", f"/pc/{self.pc.pk}/modifier/", f"/pc/{self.pc.pk}/supprimer/", "/recommandations/analyser/", "/deconnexion/"):
            with self.subTest(url=url):
                self.assertEqual(client.post(url, self.payload()).status_code, 403)

    def test_search_filters_and_counts_use_owner_data_only(self):
        self.pc.ram_gb = 4
        self.pc.save()
        PC.objects.create(owner=self.other, name="PC secret", brand="HP", model="Secret", operating_system="Linux", ram_gb=16, storage_gb=512)
        response = self.client.get("/?q=Latitude&status=attention&type=laptop")
        self.assertContains(response, "PC principal")
        self.assertEqual(response.context["total"], 1)
        self.assertEqual(response.context["attention"], 1)
        self.assertEqual(self.client.get("/?q=introuvable").context["page_obj"].paginator.count, 0)

    def test_empty_states_and_invalid_pagination_render(self):
        self.client.force_login(self.other)
        for url in ("/?page=999", "/?page=bad", "/historique/?pc=bad", "/recommandations/?priority=high"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_pc_names_and_notes_are_html_escaped(self):
        self.pc.name = '<script>alert("test")</script>'
        self.pc.notes = "<img src=x onerror=alert(1)>"
        self.pc.save()
        response = self.client.get(self.pc.get_absolute_url())
        self.assertNotContains(response, self.pc.name)
        self.assertContains(response, "&lt;script&gt;")
        self.assertContains(response, "&lt;img src=x")

    def test_seed_command_is_idempotent_and_preserves_changes(self):
        output = StringIO()
        call_command("seed_demo", "--with-admin", stdout=output)
        demo = get_user_model().objects.get(username="demo")
        demo_pc = demo.pcs.first()
        demo_pc.name = "Nom conservé"
        demo_pc.save()
        call_command("seed_demo", "--with-admin", stdout=output)
        demo_pc.refresh_from_db()
        self.assertEqual(demo_pc.name, "Nom conservé")
        self.assertEqual(demo.pcs.count(), 3)
        self.assertEqual(MaintenanceRecord.objects.filter(pc__owner=demo).count(), 4)
        self.assertTrue(demo.check_password("AtelierPC2026!"))
