from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from decimal import Decimal
from io import BytesIO, StringIO
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from maintenance.models import MaintenanceRecord, PC
from .models import Appointment, BookingSlot, Intervention, Invoice, PartLine, Technician
from .services import book_appointment, cancel_appointment, save_intervention, update_status


def future_start(hour=10, offset=2):
    day = timezone.localdate() + timedelta(days=offset)
    while day.weekday() == 6:
        day += timedelta(days=1)
    return timezone.make_aware(datetime.combine(day, time(hour)))


def make_pc(owner, name="PC de test"):
    return PC.objects.create(owner=owner, name=name, brand="Dell", model="Latitude", operating_system="Ubuntu", ram_gb=16, storage_gb=512, purchased_on=timezone.localdate() - timedelta(days=60))


class AppointmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.client_user = User.objects.create_user("client_rdv", password="ClientTest2026!", first_name="Client", last_name="Atelier", email="client@example.test")
        cls.other_client = User.objects.create_user("autre_client", password="ClientTest2026!")
        cls.tech_user = User.objects.create_user("technicien_test", password="TechTest2026!", first_name="Amine")
        cls.other_tech_user = User.objects.create_user("autre_technicien", password="TechTest2026!", first_name="Sarra")
        cls.admin_user = User.objects.create_user("admin_rdv", password="AdminTest2026!", is_staff=True)
        cls.technician = Technician.objects.create(user=cls.tech_user)
        cls.other_technician = Technician.objects.create(user=cls.other_tech_user)
        cls.pc = make_pc(cls.client_user, "PC étudiant")
        cls.other_pc = make_pc(cls.other_client, "PC confidentiel")

    def setUp(self):
        self.client.force_login(self.client_user)

    def data(self, **changes):
        data = {"pc": self.pc, "technician": self.technician, "starts_at": future_start(), "category": "preventive", "reason": "Nettoyage du ventilateur", "description": "Contrôler la ventilation et les températures."}
        data.update(changes)
        return data

    def payload(self, **changes):
        data = {"pc": self.pc.pk, "technician": self.technician.pk, "date": future_start().date().isoformat(), "time": "10:00", "category": "preventive", "reason": "Nettoyage du ventilateur", "description": "Contrôler le PC."}
        data.update(changes)
        return data

    def book(self, **changes):
        return book_appointment(self.client_user, self.data(**changes))

    def diagnose(self, appointment):
        update_status(self.tech_user, appointment.pk, "confirmed")
        update_status(self.tech_user, appointment.pk, "diagnosis")

    def complete(self, appointment=None, **changes):
        appointment = appointment or self.book()
        self.diagnose(appointment)
        data = {"diagnosis": "Poussière dans le ventilateur. Mémoire vérifiée.", "solution": "Nettoyage, contrôle et test final effectués.", "labour_cost": Decimal("25.125")}
        data.update(changes)
        parts = [{"name": "SSD de remplacement", "quantity": 2, "unit_price": Decimal("40.100")}]
        save_intervention(self.tech_user, appointment.pk, data, parts, complete=True)
        appointment.refresh_from_db()
        return appointment

    def work_payload(self, **changes):
        data = {"diagnosis": "Ventilateur nettoyé", "solution": "Essai réalisé", "labour_cost": "25.125", "parts-TOTAL_FORMS": "1", "parts-INITIAL_FORMS": "0", "parts-MIN_NUM_FORMS": "0", "parts-MAX_NUM_FORMS": "20", "parts-0-name": "SSD", "parts-0-quantity": "2", "parts-0-unit_price": "40.100", "action": "save"}
        data.update(changes)
        return data

    def test_client_booking_creates_real_reservation_and_intervention(self):
        response = self.client.post(reverse("appointments:create"), self.payload())
        appointment = Appointment.objects.get()
        self.assertRedirects(response, appointment.get_absolute_url())
        self.assertEqual(appointment.client, self.client_user)
        self.assertEqual(appointment.status, "pending")
        self.assertEqual(BookingSlot.objects.get().appointment, appointment)
        self.assertTrue(Intervention.objects.filter(appointment=appointment).exists())

    def test_cannot_book_someone_elses_pc(self):
        response = self.client.post(reverse("appointments:create"), self.payload(pc=self.other_pc.pk))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(Appointment.objects.exists())
        with self.assertRaises(PermissionDenied):
            self.book(pc=self.other_pc)

    def test_technician_and_pc_cannot_be_double_booked(self):
        self.book()
        with self.assertRaises(ValidationError):
            book_appointment(self.other_client, self.data(pc=self.other_pc))
        with self.assertRaises(ValidationError):
            self.book(technician=self.other_technician)
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(BookingSlot.objects.count(), 1)

    def test_past_closed_day_non_hour_and_out_of_hours_are_rejected(self):
        sunday = timezone.localdate() + timedelta(days=(6 - timezone.localdate().weekday()) % 7 + 7)
        invalid = [timezone.now() - timedelta(hours=1), future_start(hour=8), future_start(hour=18), future_start().replace(minute=30), timezone.make_aware(datetime.combine(sunday, time(10))), future_start(offset=370)]
        for starts_at in invalid:
            with self.subTest(starts_at=starts_at), self.assertRaises(ValidationError):
                self.book(starts_at=starts_at)
        self.assertFalse(Appointment.objects.exists())

    def test_unavailable_technician_cannot_receive_booking(self):
        self.technician.is_available = False
        self.technician.save()
        with self.assertRaises(ValidationError):
            self.book()

    def test_availability_marks_occupied_slots_and_excludes_current_booking(self):
        appointment = self.book()
        url = reverse("appointments:availability")
        params = {"technician": self.technician.pk, "date": future_start().date().isoformat(), "pc": self.pc.pk}
        data = self.client.get(url, params).json()
        self.assertFalse(next(slot for slot in data["slots"] if slot["value"] == "10:00")["available"])
        params["appointment"] = appointment.pk
        data = self.client.get(url, params).json()
        self.assertTrue(next(slot for slot in data["slots"] if slot["value"] == "10:00")["available"])
        params["pc"] = self.other_pc.pk
        self.assertEqual(self.client.get(url, params).status_code, 404)

    def test_availability_rejects_invalid_input_and_foreign_appointment(self):
        appointment = self.book()
        self.assertEqual(self.client.get(reverse("appointments:availability"), {"technician": self.technician.pk, "date": "invalide"}).status_code, 400)
        self.client.force_login(self.other_client)
        self.assertEqual(self.client.get(reverse("appointments:availability"), {"technician": self.technician.pk, "date": future_start().date().isoformat(), "appointment": appointment.pk}).status_code, 404)

    def test_modification_moves_reservation_and_requests_confirmation(self):
        appointment = self.book()
        update_status(self.tech_user, appointment.pk, "confirmed")
        modified = book_appointment(self.client_user, self.data(starts_at=future_start(hour=11)), appointment.pk)
        self.assertEqual(modified.status, "pending")
        self.assertEqual(BookingSlot.objects.get().starts_at, future_start(hour=11))
        self.assertEqual(Appointment.objects.count(), 1)

    def test_assigned_technician_can_modify_and_cancel(self):
        appointment = self.book()
        book_appointment(self.tech_user, self.data(starts_at=future_start(hour=11)), appointment.pk)
        cancel_appointment(self.tech_user, appointment.pk)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "cancelled")
        self.assertFalse(BookingSlot.objects.exists())

    def test_cancel_get_is_confirmation_and_post_releases_slot(self):
        appointment = self.book()
        url = reverse("appointments:cancel", args=[appointment.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "pending")
        self.assertRedirects(self.client.post(url), appointment.get_absolute_url())
        self.assertFalse(BookingSlot.objects.exists())
        self.book()
        self.assertEqual(Appointment.objects.count(), 2)

    def test_repair_and_closed_statuses_block_modification_and_cancellation(self):
        appointment = self.book()
        self.diagnose(appointment)
        update_status(self.tech_user, appointment.pk, "repair")
        for operation in (lambda: cancel_appointment(self.client_user, appointment.pk), lambda: book_appointment(self.client_user, self.data(starts_at=future_start(hour=11)), appointment.pk)):
            with self.assertRaises(ValidationError):
                operation()
        self.complete_from_repair(appointment)
        with self.assertRaises(ValidationError):
            cancel_appointment(self.tech_user, appointment.pk)

    def complete_from_repair(self, appointment):
        save_intervention(self.tech_user, appointment.pk, {"diagnosis": "Diagnostic effectué", "solution": "Réparation terminée", "labour_cost": Decimal("1.000")}, [], complete=True)

    def test_client_and_other_technician_cannot_change_status_or_work(self):
        appointment = self.book()
        for actor in (self.client_user, self.other_tech_user):
            self.client.force_login(actor)
            expected = 403 if actor == self.client_user else 404
            self.assertEqual(self.client.post(reverse("appointments:status_update", args=[appointment.pk]), {"status": "confirmed"}).status_code, expected)
            self.assertEqual(self.client.post(reverse("appointments:intervention_update", args=[appointment.pk]), self.work_payload()).status_code, expected)

    def test_other_clients_cannot_read_modify_cancel_or_list_an_appointment(self):
        appointment = self.book()
        self.client.force_login(self.other_client)
        for route in ("detail", "update", "cancel"):
            url = reverse(f"appointments:{route}", args=[appointment.pk])
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, self.payload()).status_code, 404)
        self.assertNotContains(self.client.get(reverse("appointments:list")), appointment.reason)

    def test_completion_creates_history_and_exact_frozen_invoice_once(self):
        appointment = self.complete()
        invoice = Invoice.objects.get()
        self.assertEqual(appointment.status, "completed")
        self.assertEqual(invoice.total_amount, Decimal("105.325"))
        self.assertEqual(invoice.snapshot["parts_total"], "80.200")
        self.assertEqual(MaintenanceRecord.objects.filter(pc=self.pc).count(), 1)
        self.assertIn("Nettoyage", MaintenanceRecord.objects.get().description)
        update_status(self.tech_user, appointment.pk, "completed")
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(MaintenanceRecord.objects.count(), 1)
        original_snapshot = invoice.snapshot
        self.pc.name = "Nom modifié après clôture"
        self.pc.save()
        invoice.refresh_from_db()
        self.assertEqual(invoice.snapshot, original_snapshot)
        self.assertEqual(invoice.snapshot["pc"]["name"], "PC étudiant")

    def test_completion_without_diagnosis_and_solution_rolls_back(self):
        appointment = self.book()
        self.diagnose(appointment)
        with self.assertRaises(ValidationError):
            save_intervention(self.tech_user, appointment.pk, {"diagnosis": "", "solution": "Test", "labour_cost": Decimal("25.000")}, [], complete=True)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "diagnosis")
        self.assertFalse(Invoice.objects.exists())
        self.assertFalse(MaintenanceRecord.objects.exists())
        self.assertEqual(Intervention.objects.get().labour_cost, Decimal("0.000"))

    def test_workflow_cannot_skip_or_reverse_states(self):
        appointment = self.book()
        with self.assertRaises(ValidationError):
            update_status(self.tech_user, appointment.pk, "completed")
        self.diagnose(appointment)
        with self.assertRaises(ValidationError):
            update_status(self.tech_user, appointment.pk, "pending")

    def test_closed_work_and_costs_cannot_be_overwritten(self):
        appointment = self.complete()
        with self.assertRaises(ValidationError):
            save_intervention(self.tech_user, appointment.pk, {"diagnosis": "Modifié", "solution": "Modifié", "labour_cost": Decimal("99.000")}, [])
        self.client.force_login(self.tech_user)
        self.client.post(reverse("appointments:intervention_update", args=[appointment.pk]), self.work_payload(labour_cost="999.000"))
        self.assertEqual(Invoice.objects.get().total_amount, Decimal("105.325"))

    def test_intervention_post_saves_parts_and_closes_via_named_action(self):
        appointment = self.book()
        self.diagnose(appointment)
        self.client.force_login(self.tech_user)
        response = self.client.post(reverse("appointments:intervention_update", args=[appointment.pk]), self.work_payload(action="complete"))
        self.assertRedirects(response, appointment.get_absolute_url())
        self.assertEqual(Invoice.objects.get().total_amount, Decimal("105.325"))

    def test_negative_cost_and_tampered_part_id_do_not_write_data(self):
        appointment = self.book()
        self.client.force_login(self.tech_user)
        url = reverse("appointments:intervention_update", args=[appointment.pk])
        response = self.client.post(url, self.work_payload(**{"parts-0-unit_price": "-1"}))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["parts_formset"].errors)
        self.assertFalse(PartLine.objects.exists())
        foreign = book_appointment(self.other_client, self.data(pc=self.other_pc, technician=self.other_technician))
        part = PartLine.objects.create(intervention=foreign.intervention, name="Pièce privée", quantity=1, unit_price=Decimal("10.000"))
        response = self.client.post(url, self.work_payload(**{"parts-INITIAL_FORMS": "1", "parts-0-id": part.pk}))
        self.assertEqual(response.status_code, 200)
        part.refresh_from_db()
        self.assertEqual(part.name, "Pièce privée")
        self.assertFalse(appointment.intervention.parts.exists())

    def test_pdf_exports_are_readable_and_contain_correct_details(self):
        appointment = self.complete()
        invoice = Invoice.objects.get()
        for kind in ("report", "invoice"):
            response = self.client.get(reverse("appointments:pdf", args=[invoice.pk, kind]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertIn("attachment;", response["Content-Disposition"])
            payload = b"".join(response.streaming_content)
            self.assertTrue(payload.startswith(b"%PDF-"))
            text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(payload)).pages)
            for value in (invoice.number, "PC étudiant", "SSD de remplacement", "105,325 TND"):
                self.assertIn(value, text)
            if kind == "report":
                self.assertIn("Mémoire vérifiée", text)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertContains(self.client.get(reverse("maintenance:history")), "Rapport PDF")

    def test_pdf_exports_are_private_to_client_and_administrator(self):
        self.complete()
        invoice = Invoice.objects.get()
        url = reverse("appointments:pdf", args=[invoice.pk, "invoice"])
        for actor in (self.other_client, self.other_tech_user, self.tech_user):
            self.client.force_login(actor)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertNotContains(self.client.get(reverse("appointments:documents")), invoice.number)
        self.client.force_login(self.admin_user)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get(reverse("appointments:documents")), invoice.number)

    def test_long_report_paginates_and_escapes_markup(self):
        appointment = self.complete(diagnosis=("Diagnostic détaillé : ventilation et mémoire.\n" * 70) + "<script>texte</script>", solution="Contrôle final et nettoyage.\n" * 100)
        invoice = Invoice.objects.get()
        response = self.client.get(reverse("appointments:pdf", args=[invoice.pk, "report"]))
        payload = b"".join(response.streaming_content)
        reader = PdfReader(BytesIO(payload))
        self.assertGreater(len(reader.pages), 1)
        self.assertIn("<script>texte</script>", "\n".join(page.extract_text() for page in reader.pages))
        self.assertNotIn(b"/JavaScript", payload)

    def test_pages_render_for_client_technician_and_admin(self):
        appointment = self.book()
        for actor in (self.client_user, self.tech_user, self.admin_user):
            self.client.force_login(actor)
            for url in (reverse("appointments:list"), reverse("appointments:create"), appointment.get_absolute_url(), reverse("appointments:documents")):
                with self.subTest(actor=actor.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_mutations_require_csrf_and_status_get_is_not_allowed(self):
        appointment = self.book()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.tech_user)
        for route in ("cancel", "update", "status_update", "intervention_update"):
            self.assertEqual(client.post(reverse(f"appointments:{route}", args=[appointment.pk]), self.payload()).status_code, 403)
        self.assertEqual(client.post(reverse("appointments:create"), self.payload()).status_code, 403)
        for route in ("status_update", "intervention_update"):
            self.assertEqual(self.client.get(reverse(f"appointments:{route}", args=[appointment.pk])).status_code, 405)

    def test_pc_with_appointment_cannot_be_deleted(self):
        self.book()
        response = self.client.post(reverse("maintenance:pc_delete", args=[self.pc.pk]))
        self.assertRedirects(response, self.pc.get_absolute_url())
        self.assertTrue(PC.objects.filter(pk=self.pc.pk).exists())

    def test_anonymous_users_are_redirected_to_login(self):
        self.client.logout()
        for route in ("list", "create", "documents", "availability"):
            self.assertEqual(self.client.get(reverse(f"appointments:{route}")).status_code, 302)

    def test_login_opens_the_workspace_matching_the_user_role(self):
        for actor, password, destination in [(self.client_user, "ClientTest2026!", "/"), (self.tech_user, "TechTest2026!", "/rendez-vous/"), (self.admin_user, "AdminTest2026!", "/backoffice/")]:
            self.client.logout()
            response = self.client.post(reverse("login"), {"username": actor.username, "password": password})
            self.assertRedirects(response, destination)

    def test_seed_technicians_is_idempotent_and_preserves_existing_passwords(self):
        output = StringIO()
        call_command("seed_technicians", stdout=output)
        tech = get_user_model().objects.get(username="tech_amine")
        tech.set_password("MotDePasseConserve2026!")
        tech.save()
        call_command("seed_technicians", stdout=output)
        tech.refresh_from_db()
        self.assertTrue(tech.check_password("MotDePasseConserve2026!"))
        self.assertEqual(Technician.objects.filter(user__username__in=["tech_amine", "tech_sarra"]).count(), 2)


class ConcurrentBookingTests(TransactionTestCase):
    def test_simultaneous_requests_only_reserve_one_technician_slot(self):
        User = get_user_model()
        tech_user = User.objects.create_user("concurrent_tech")
        technician = Technician.objects.create(user=tech_user)
        users = [User.objects.create_user(f"concurrent_client_{i}") for i in range(2)]
        pcs = [make_pc(user, f"PC {i}") for i, user in enumerate(users)]
        barrier = Barrier(2)

        def attempt(index):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET SESSION innodb_lock_wait_timeout=5")
                barrier.wait(timeout=5)
                book_appointment(users[index], {"pc": pcs[index], "technician": technician, "starts_at": future_start(), "category": "preventive", "reason": "Test simultané", "description": ""})
                return "reserved"
            except ValidationError:
                return "unavailable"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(attempt, i) for i in range(2)]
            results = [future.result(timeout=15) for future in futures]
        self.assertCountEqual(results, ["reserved", "unavailable"])
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(BookingSlot.objects.count(), 1)
        self.assertEqual(Intervention.objects.count(), 1)
