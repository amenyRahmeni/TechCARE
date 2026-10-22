from decimal import Decimal

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from appointments.models import Appointment, BookingSlot, Invoice, Technician
from appointments.services import book_appointment, save_intervention, update_status
from appointments.tests import future_start, make_pc
from maintenance.models import MaintenanceRule, Recommendation

User = get_user_model()


class BackofficeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("admin_bo", "admin@example.test", "AdminBackoffice2026!")
        cls.staff = User.objects.create_user("staff_bo", password="StaffBackoffice2026!", is_staff=True)
        cls.customer = User.objects.create_user("client_bo", password="ClientBackoffice2026!", first_name="Nour")
        cls.tech_user = User.objects.create_user("tech_bo", password="TechBackoffice2026!", first_name="Amine")
        cls.tech = Technician.objects.create(user=cls.tech_user)
        cls.pc = make_pc(cls.customer, "PC du client")

    def setUp(self):
        self.client.force_login(self.admin)

    def account_payload(self, **changes):
        data = {"username": "nouveau_client", "first_name": "Inès", "last_name": "Test", "email": "ines@example.test", "role": "client", "password1": "CompteSolide2026!", "password2": "CompteSolide2026!"}
        data.update(changes)
        return data

    def booking(self):
        return book_appointment(self.admin, {"pc": self.pc, "technician": self.tech, "starts_at": future_start(), "category": "preventive", "reason": "Entretien du PC", "description": "Nettoyer le ventilateur."})

    def pc_payload(self, **changes):
        data = {"owner": self.customer.pk, "name": "PC de bureau", "brand": "Dell", "model": "Optiplex", "device_type": "desktop", "serial_number": "BO-001", "operating_system": "Ubuntu", "ram_gb": 16, "storage_gb": 512, "storage_type": "SSD"}
        data.update(changes)
        return data

    def test_anonymous_redirected_and_nonstaff_denied_on_all_admin_routes(self):
        appointment = self.booking()
        routes = [("dashboard", []), ("accounts", []), ("account_create", []), ("account_update", [self.customer.pk]), ("account_state", [self.customer.pk]), ("technicians", []), ("pcs", []), ("pc_create", []), ("pc_detail", [self.pc.pk]), ("pc_update", [self.pc.pk]), ("pc_delete", [self.pc.pk]), ("rules", []), ("rule_create", []), ("list", []), ("create", []), ("detail", [appointment.pk]), ("update", [appointment.pk]), ("cancel", [appointment.pk]), ("status_update", [appointment.pk]), ("intervention_update", [appointment.pk]), ("availability", []), ("documents", []), ("pdf", [1, "invoice"])]
        anonymous = Client()
        for name, args in routes:
            url = reverse(f"backoffice:{name}", args=args)
            self.assertEqual(anonymous.get(url).status_code, 302, name)
            for actor in (self.customer, self.tech_user):
                self.client.force_login(actor)
                self.assertEqual(self.client.get(url).status_code, 403, name)
                self.assertEqual(self.client.post(url, {}).status_code, 403, name)

    def test_dashboard_empty_and_populated_metrics_are_from_database(self):
        response = self.client.get(reverse("backoffice:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["counts"]["pcs"], 1)
        self.assertEqual(response.context["counts"]["clients"], 1)
        self.assertEqual(response.context["completion"], 0)
        self.assertEqual(len(response.context["chart"]), 6)
        appointment = self.booking()
        update_status(self.admin, appointment.pk, "confirmed")
        update_status(self.admin, appointment.pk, "diagnosis")
        save_intervention(self.admin, appointment.pk, {"diagnosis": "Poussière", "solution": "Nettoyage", "labour_cost": Decimal("30.125")}, [], complete=True)
        response = self.client.get(reverse("backoffice:dashboard"))
        self.assertEqual(response.context["counts"]["monthly_revenue"], Decimal("30.125"))
        self.assertEqual(response.context["completion"], 100)
        self.assertEqual(response.context["chart"][-1]["amount"], Decimal("30.125"))
        self.assertEqual(response.context["chart"][-1]["height"], 100)
        self.assertIn("no-store", response["Cache-Control"])

    def test_account_create_hashes_password_and_audits_without_secrets(self):
        response = self.client.post(reverse("backoffice:account_create"), self.account_payload())
        self.assertRedirects(response, reverse("backoffice:accounts"))
        account = User.objects.get(username="nouveau_client")
        self.assertTrue(account.check_password("CompteSolide2026!"))
        self.assertFalse(account.is_staff)
        self.assertNotIn("CompteSolide", LogEntry.objects.get().change_message)

    def test_edit_account_retains_password_and_ignores_privilege_injection(self):
        old_hash = self.customer.password
        response = self.client.post(reverse("backoffice:account_update", args=[self.customer.pk]), self.account_payload(username=self.customer.username, password1="", password2="", is_superuser="on", is_staff="on", is_active=""))
        self.assertEqual(response.status_code, 302)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.password, old_hash)
        self.assertEqual(self.customer.first_name, "Inès")
        self.assertFalse(self.customer.is_superuser)
        self.assertFalse(self.customer.is_staff)
        self.assertTrue(self.customer.is_active)

    def test_password_mismatch_weak_password_and_duplicate_identifier_rejected(self):
        for changes in ({"password2": "different"}, {"password1": "12345678", "password2": "12345678"}, {"username": self.customer.username}):
            response = self.client.post(reverse("backoffice:account_create"), self.account_payload(**changes))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="nouveau_client").exists())

    def test_staff_cannot_grant_admin_role_or_edit_admin_accounts(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("backoffice:account_create"), self.account_payload(role="admin"))
        self.assertTrue(response.context["form"].errors)
        for name in ("account_update", "account_state"):
            self.assertEqual(self.client.post(reverse(f"backoffice:{name}", args=[self.admin.pk]), {}).status_code, 403)
        self.assertFalse(User.objects.filter(username="nouveau_client").exists())

    def test_self_suspension_and_self_demotion_blocked(self):
        self.client.post(reverse("backoffice:account_state", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        response = self.client.post(reverse("backoffice:account_update", args=[self.admin.pk]), self.account_payload(username=self.admin.username, role="client", password1="", password2=""))
        self.assertTrue(response.context["form"].errors)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_staff)

    def test_suspend_requires_post_and_blocks_login_without_deleting_data(self):
        url = reverse("backoffice:account_state", args=[self.customer.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)
        self.client.post(url)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)
        self.assertFalse(Client().login(username=self.customer.username, password="ClientBackoffice2026!"))
        self.pc.refresh_from_db()
        self.assertEqual(self.pc.owner_id, self.customer.pk)
        self.client.post(url)
        self.assertTrue(Client().login(username=self.customer.username, password="ClientBackoffice2026!"))

    def test_mutations_require_csrf(self):
        guarded = Client(enforce_csrf_checks=True)
        guarded.force_login(self.admin)
        for url, payload in [(reverse("backoffice:account_state", args=[self.customer.pk]), {}), (reverse("backoffice:account_create"), self.account_payload()), (reverse("backoffice:pc_delete", args=[self.pc.pk]), {})]:
            self.assertEqual(guarded.post(url, payload).status_code, 403)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)

    def test_create_technician_and_update_availability(self):
        response = self.client.post(reverse("backoffice:account_create"), self.account_payload(role="technician", specialty="Réparation matérielle", is_available="on"))
        self.assertEqual(response.status_code, 302)
        technician = Technician.objects.get(user__username="nouveau_client")
        self.assertTrue(technician.is_available)
        response = self.client.post(reverse("backoffice:account_update", args=[technician.user_id]), self.account_payload(role="technician", specialty="Réseaux", password1="", password2=""))
        self.assertEqual(response.status_code, 302)
        technician.refresh_from_db()
        self.assertFalse(technician.is_available)
        self.assertEqual(technician.specialty, "Réseaux")

    def test_technician_with_history_cannot_lose_profile(self):
        self.booking()
        response = self.client.post(reverse("backoffice:account_update", args=[self.tech_user.pk]), self.account_payload(username=self.tech_user.username, role="client", password1="", password2=""))
        self.assertIn("role", response.context["form"].errors)
        self.assertTrue(Technician.objects.filter(pk=self.tech.pk).exists())

    def test_account_search_filters_and_pagination(self):
        response = self.client.get(reverse("backoffice:accounts"), {"role": "client", "q": "Nour"})
        self.assertEqual([item.pk for item in response.context["page_obj"]], [self.customer.pk])
        User.objects.bulk_create([User(username=f"client_extra_{index}", password="!") for index in range(15)])
        response = self.client.get(reverse("backoffice:accounts"), {"role": "client", "page": "2"})
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertIn("role=client", response.context["page_query"])

    def test_admin_can_create_and_edit_client_pc_without_changing_owner(self):
        response = self.client.post(reverse("backoffice:pc_create"), self.pc_payload())
        self.assertEqual(response.status_code, 302)
        pc = self.customer.pcs.get(serial_number="BO-001")
        response = self.client.post(reverse("backoffice:pc_update", args=[pc.pk]), self.pc_payload(owner=self.admin.pk, name="PC modifié"))
        self.assertEqual(response.status_code, 302)
        pc.refresh_from_db()
        self.assertEqual(pc.owner_id, self.customer.pk)
        self.assertEqual(pc.name, "PC modifié")
        self.assertContains(self.client.get(reverse("backoffice:pc_detail", args=[pc.pk])), "PC modifié")

    def test_invalid_owner_and_duplicate_serial_rejected(self):
        self.client.post(reverse("backoffice:pc_create"), self.pc_payload())
        for payload in [self.pc_payload(), self.pc_payload(owner=999999, serial_number="OTHER")]:
            response = self.client.post(reverse("backoffice:pc_create"), payload)
            self.assertTrue(response.context["form"].errors)
        self.assertEqual(self.customer.pcs.count(), 2)

    def test_pc_deletion_confirms_and_preserves_booked_pc(self):
        url = reverse("backoffice:pc_delete", args=[self.pc.pk])
        self.client.get(url)
        self.pc.refresh_from_db()
        self.booking()
        response = self.client.post(url)
        self.assertRedirects(response, reverse("backoffice:pc_detail", args=[self.pc.pk]))
        self.pc.refresh_from_db()
        self.assertFalse(LogEntry.objects.filter(action_flag=3).exists())
        spare = make_pc(self.customer, "PC à supprimer")
        self.client.post(reverse("backoffice:pc_delete", args=[spare.pk]))
        self.assertFalse(self.customer.pcs.filter(pk=spare.pk).exists())

    def test_rule_update_recalculates_recommendations(self):
        rule = MaintenanceRule.objects.create(code="bo-test-ram", title="Ajouter de la RAM", description="Tester la RAM", criterion="ram_below", threshold=32, priority="high")
        self.assertTrue(Recommendation.objects.get(pc=self.pc, rule=rule).is_active)
        response = self.client.post(reverse("backoffice:rule_update", args=[rule.pk]), {"code": rule.code, "title": rule.title, "description": rule.description, "criterion": "ram_below", "threshold": 8, "priority": "medium", "is_active": "on"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Recommendation.objects.get(pc=self.pc, rule=rule).is_active)

    def test_workflow_links_redirects_and_pdf_stay_in_backoffice(self):
        appointment = self.booking()
        detail = reverse("backoffice:detail", args=[appointment.pk])
        response = self.client.get(reverse("backoffice:list"))
        self.assertContains(response, detail)
        self.assertContains(response, "Navigation de l’administration")
        response = self.client.post(reverse("backoffice:status_update", args=[appointment.pk]), {"status": "confirmed"})
        self.assertRedirects(response, detail)
        self.client.post(reverse("backoffice:status_update", args=[appointment.pk]), {"status": "diagnosis"})
        payload = {"diagnosis": "Ventilateur encrassé", "solution": "Nettoyage effectué", "labour_cost": "25.125", "parts-TOTAL_FORMS": "0", "parts-INITIAL_FORMS": "0", "parts-MIN_NUM_FORMS": "0", "parts-MAX_NUM_FORMS": "20", "action": "complete"}
        self.assertRedirects(self.client.post(reverse("backoffice:intervention_update", args=[appointment.pk]), payload), detail)
        invoice = Invoice.objects.get()
        self.assertContains(self.client.get(reverse("backoffice:documents")), detail)
        response = self.client.get(reverse("backoffice:pdf", args=[invoice.pk, "invoice"]))
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF"))

    def test_booking_creation_and_cancel_remain_in_admin_navigation(self):
        starts = future_start()
        response = self.client.post(reverse("backoffice:create"), {"pc": self.pc.pk, "technician": self.tech.pk, "date": starts.date().isoformat(), "time": "10:00", "category": "preventive", "reason": "Réservation admin", "description": ""})
        appointment = Appointment.objects.get()
        detail = reverse("backoffice:detail", args=[appointment.pk])
        self.assertRedirects(response, detail)
        self.assertRedirects(self.client.post(reverse("backoffice:cancel", args=[appointment.pk])), detail)
        self.assertFalse(BookingSlot.objects.exists())

    def test_admin_pages_render_with_existing_data_and_escape_user_input(self):
        self.customer.first_name = '<script>alert("test")</script>'
        self.customer.save()
        for name in ("dashboard", "accounts", "account_create", "technicians", "pcs", "pc_create", "rules", "rule_create", "list", "create", "documents"):
            response = self.client.get(reverse(f"backoffice:{name}"))
            self.assertEqual(response.status_code, 200, name)
            self.assertTemplateUsed(response, "backoffice/base.html")
        response = self.client.get(reverse("backoffice:accounts"))
        self.assertNotContains(response, '<script>alert("test")</script>')
        self.assertContains(response, "&lt;script&gt;")
