from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from maintenance.models import MaintenanceRecord, PC, Recommendation
from notifications.models import Notification
from repairs.models import RepairRequest
from repairs.services import assign_technician, create_request
from .models import Appointment, Invoice, Technician
from .services import book_appointment, save_intervention, update_status
from .tests import future_start, make_pc


class TechnicianWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.customer = User.objects.create_user("role_customer")
        cls.other_customer = User.objects.create_user("role_other_customer")
        cls.tech_user = User.objects.create_user("role_technician")
        cls.other_tech_user = User.objects.create_user("role_other_technician")
        cls.admin = User.objects.create_user("role_admin", is_staff=True)
        cls.technician = Technician.objects.create(user=cls.tech_user)
        cls.other_technician = Technician.objects.create(user=cls.other_tech_user)
        cls.pc = make_pc(cls.customer, "PC client assigné")
        cls.private_pc = make_pc(cls.other_customer, "PC sans affectation")
        cls.legacy_pc = make_pc(cls.tech_user, "Ancien PC personnel du technicien")
        cls.appointment = book_appointment(cls.customer, {"pc": cls.pc, "technician": cls.technician, "starts_at": future_start(), "category": "hardware", "reason": "Diagnostic du PC client", "description": "Le PC chauffe."})
        cls.repair = create_request(cls.customer, {"pc": cls.pc, "technician": cls.technician, "problem": "heat", "description": "Surchauffe", "technical_notes": ""})
        assign_technician(cls.customer, cls.repair.pk, cls.technician.pk)
        cls.legacy_appointment = Appointment.objects.create(client=cls.tech_user, pc=cls.legacy_pc, technician=cls.other_technician, starts_at=future_start(hour=11), reason="Ancien rendez-vous client du technicien")
        cls.legacy_repair = RepairRequest.objects.create(client=cls.tech_user, pc=cls.legacy_pc, technician=cls.other_technician, problem="software", description="Ancienne demande en tant que client", status="assigned")
        MaintenanceRecord.objects.create(pc=cls.pc, title="Entretien précédent", kind="preventive", description="Nettoyage et contrôle", completed_on=timezone.localdate())

    def setUp(self):
        self.client.force_login(self.tech_user)

    def test_root_redirects_technician_to_assigned_interventions(self):
        response = self.client.get(reverse("maintenance:pc_list"), follow=True)
        self.assertRedirects(response, reverse("appointments:list"))
        self.assertContains(response, "Mes interventions")
        self.assertNotContains(response, "Ajouter un PC")

    def test_technician_navigation_only_contains_work_features(self):
        response = self.client.get(reverse("appointments:list"))
        for text in ["Mes interventions", "Mes réparations", "Vitrine composants", "Mes annonces", "Stock de l’atelier", "Notifications"]:
            self.assertContains(response, text)
        for path in [reverse("maintenance:pc_list"), reverse("maintenance:history"), reverse("maintenance:recommendations"), reverse("appointments:documents")]:
            self.assertNotContains(response, f'href="{path}"')
        for text in ["Mes rendez-vous client", "Prendre rendez-vous", "Déclarer une panne", "Ajouter un PC", "Voir mes conseils"]:
            self.assertNotContains(response, text)
        self.assertContains(response, 'class="brand" href="/rendez-vous/"')

    def test_client_actions_are_denied_on_get_and_post_even_for_legacy_owned_pc(self):
        paths = [reverse("maintenance:pc_create"), reverse("maintenance:pc_update", args=[self.legacy_pc.pk]), reverse("maintenance:pc_delete", args=[self.legacy_pc.pk]), reverse("maintenance:history"), reverse("maintenance:recommendations"), reverse("appointments:create"), reverse("appointments:documents"), reverse("repairs:create")]
        before = (PC.objects.count(), Appointment.objects.count(), RepairRequest.objects.count())
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 403, path)
            self.assertEqual(self.client.post(path, {}).status_code, 403, path)
        self.assertEqual(self.client.post(reverse("maintenance:analyze")).status_code, 403)
        self.assertEqual(before, (PC.objects.count(), Appointment.objects.count(), RepairRequest.objects.count()))

    def test_booking_and_panne_services_reject_technician_as_new_client(self):
        with self.assertRaises(PermissionDenied):
            book_appointment(self.tech_user, {"pc": self.legacy_pc, "technician": self.other_technician, "starts_at": future_start(hour=12), "category": "hardware", "reason": "Nouvelle réservation interdite", "description": ""})
        with self.assertRaises(PermissionDenied):
            create_request(self.tech_user, {"pc": self.legacy_pc, "problem": "heat", "description": "Panne personnelle interdite", "technical_notes": ""})

    def test_technician_cannot_switch_to_legacy_client_appointment_scope(self):
        for query in ("", "?scope=client", "?scope=all"):
            response = self.client.get(reverse("appointments:list") + query)
            self.assertContains(response, self.appointment.reason)
            self.assertNotContains(response, self.legacy_appointment.reason)
            self.assertEqual(response.context["scope"], "assigned")
        self.assertEqual(self.client.get(self.legacy_appointment.get_absolute_url()).status_code, 404)
        response = self.client.get(reverse("repairs:list"))
        self.assertContains(response, self.repair.reference)
        self.assertNotContains(response, self.legacy_repair.reference)
        self.assertEqual(self.client.get(self.legacy_repair.get_absolute_url()).status_code, 404)

    def test_assigned_pc_config_and_history_are_available_read_only(self):
        response = self.client.get(self.pc.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configuration technique")
        self.assertContains(response, "Consultation seule")
        self.assertContains(response, "Entretien précédent")
        self.assertNotContains(response, reverse("maintenance:pc_update", args=[self.pc.pk]))
        self.assertNotContains(response, reverse("maintenance:pc_delete", args=[self.pc.pk]))
        self.assertNotContains(response, reverse("maintenance:analyze"))
        self.assertEqual(self.client.get(self.private_pc.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(self.legacy_pc.get_absolute_url()).status_code, 404)

    def test_pc_read_access_is_revoked_after_both_jobs_are_reassigned(self):
        self.assertEqual(self.client.get(self.pc.get_absolute_url()).status_code, 200)
        assign_technician(self.customer, self.repair.pk, self.other_technician.pk)
        book_appointment(self.customer, {"pc": self.pc, "technician": self.other_technician, "starts_at": future_start(), "category": "hardware", "reason": self.appointment.reason, "description": "Le PC chauffe."}, self.appointment.pk)
        self.assertEqual(self.client.get(self.pc.get_absolute_url()).status_code, 404)

    def test_assigned_appointment_can_still_be_modified_and_cancelled(self):
        response = self.client.get(reverse("appointments:update", args=[self.appointment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["form"].fields["pc"].queryset.values_list("pk", flat=True)), [self.pc.pk])
        params = {"technician": self.technician.pk, "date": future_start().date().isoformat(), "pc": self.pc.pk, "appointment": self.appointment.pk}
        self.assertEqual(self.client.get(reverse("appointments:availability"), params).status_code, 200)
        self.assertEqual(self.client.get(reverse("appointments:availability"), {key: value for key, value in params.items() if key != "appointment"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("appointments:cancel", args=[self.appointment.pk])).status_code, 200)

    def test_client_and_administrator_keep_their_own_actions(self):
        self.client.force_login(self.customer)
        self.assertContains(self.client.get("/"), "Ajouter un PC")
        for route in ("maintenance:pc_create", "maintenance:history", "maintenance:recommendations", "appointments:create", "appointments:documents", "repairs:create"):
            self.assertEqual(self.client.get(reverse(route)).status_code, 200, route)
        self.client.force_login(self.admin)
        for route in ("backoffice:dashboard", "backoffice:pc_create", "backoffice:documents"):
            self.assertEqual(self.client.get(reverse(route)).status_code, 200, route)
        self.assertEqual(self.client.get(reverse("backoffice:create")).status_code, 403)
        self.assertEqual(self.client.get(reverse("backoffice:repair_create")).status_code, 403)

    def test_technician_pdf_downloads_and_client_pdf_actions_are_absent(self):
        update_status(self.tech_user, self.appointment.pk, "confirmed")
        update_status(self.tech_user, self.appointment.pk, "diagnosis")
        save_intervention(self.tech_user, self.appointment.pk, {"diagnosis": "Ventilateur usé", "solution": "Nettoyage et test", "labour_cost": Decimal("10.000")}, [], complete=True)
        invoice = Invoice.objects.get(intervention__appointment=self.appointment)
        self.assertEqual(self.client.get(reverse("appointments:pdf", args=[invoice.pk, "report"])).status_code, 403)
        self.assertNotContains(self.client.get(self.appointment.get_absolute_url()), "Rapport PDF")
        self.assertNotContains(self.client.get(self.pc.get_absolute_url()), "Rapport PDF")
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("appointments:pdf", args=[invoice.pk, "report"])).status_code, 200)
        self.assertContains(self.client.get(self.pc.get_absolute_url()), "Rapport PDF")

    def test_legacy_personal_recommendations_do_not_generate_technician_alerts(self):
        self.legacy_pc.ram_gb = 4
        self.legacy_pc.save()
        recommendation = Recommendation.objects.get(pc=self.legacy_pc, rule__criterion="ram_below")
        self.assertFalse(Notification.objects.filter(recipient=self.tech_user, recommendation=recommendation).exists())
        old = Notification.objects.create(recipient=self.tech_user, kind="recommendation", title="Ancien conseil personnel", message="Ancienne notification", event_key="legacy-role-rec", recommendation=recommendation)
        self.assertEqual(old.target_url(self.tech_user), reverse("appointments:list"))
