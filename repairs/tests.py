from io import BytesIO
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image
from pypdf import PdfReader

from appointments.models import Invoice, Technician
from appointments.tests import make_pc
from inventory.models import Category, SparePart
from inventory.services import use_component
from notifications.models import Notification
from .forms import AssignmentForm, RequestForm
from .models import RepairMessage, RepairRequest
from .services import assign_technician, change_status, create_request, save_report, send_message


def photo_upload():
    output = BytesIO()
    Image.new("RGB", (30, 20), "orange").save(output, "PNG")
    return SimpleUploadedFile("untrusted-name.php", output.getvalue(), content_type="application/octet-stream")


class RepairTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("repair_client")
        cls.other = User.objects.create_user("repair_other")
        cls.admin = User.objects.create_user("repair_admin", is_staff=True)
        cls.tech_user = User.objects.create_user("repair_tech")
        cls.software_user = User.objects.create_user("repair_software")
        cls.tech = Technician.objects.create(user=cls.tech_user, skills=["hardware"])
        cls.software = Technician.objects.create(user=cls.software_user, skills=["software"])
        cls.pc = make_pc(cls.owner)
        cls.other_pc = make_pc(cls.other, "PC privé")

    def create(self, **kwargs):
        data = {"pc": self.pc, "technician": self.tech, "problem": "heat", "description": "Le PC chauffe et s’arrête.", "technical_notes": "Sous charge."}
        data.update(kwargs)
        return create_request(self.owner, data)

    def diagnose(self):
        repair = self.create()
        assign_technician(self.owner, repair.pk, self.tech.pk)
        return change_status(self.tech_user, repair.pk, "diagnosis")

    def report(self):
        return {"diagnosis": "Ventilateur défectueux", "solution": "Remplacement et test thermique", "labour_cost": Decimal("25.125")}

    def test_creation_assigns_selected_technician_and_notifies_only_participants(self):
        repair = self.create()
        self.assertEqual(repair.status, "assigned")
        self.assertEqual(repair.technician_id, self.tech.pk)
        self.assertEqual(repair.events.count(), 2)
        self.assertEqual(set(Notification.objects.filter(repair=repair).values_list("recipient_id", flat=True)), {self.owner.pk, self.tech_user.pk})

    def test_client_cannot_declare_for_another_pc(self):
        with self.assertRaises(PermissionDenied):
            self.create(pc=self.other_pc)
        self.client.force_login(self.owner)
        result = self.client.post(reverse("repairs:create"), {"pc": self.other_pc.pk, "problem": "heat", "description": "Panne"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(RepairRequest.objects.count(), 0)

    def test_admin_cannot_declare_a_panne_from_either_workspace(self):
        own_pc = make_pc(self.admin, "PC du compte administrateur")
        self.client.force_login(self.admin)
        for pc in (self.pc, own_pc):
            data = {"pc": pc.pk, "problem": "heat", "description": "Déclaration interdite", "technical_notes": ""}
            for route in ("repairs:create", "backoffice:repair_create"):
                self.assertEqual(self.client.get(reverse(route)).status_code, 403)
                self.assertEqual(self.client.post(reverse(route), data).status_code, 403)
        self.assertFalse(RepairRequest.objects.exists())

    def test_admin_creation_service_denies_before_writing_photo_or_events(self):
        own_pc = make_pc(self.admin, "PC personnel du compte administrateur")
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            for pc in (self.pc, own_pc):
                with self.assertRaises(PermissionDenied):
                    create_request(self.admin, {"pc": pc, "problem": "heat", "description": "Interdit", "technical_notes": "", "photo": photo_upload()})
            self.assertEqual(list(Path(directory).rglob("*.jpg")), [])
        self.assertFalse(RepairRequest.objects.exists())

    def test_only_client_list_exposes_declaration_actions(self):
        for actor in (self.admin, self.tech_user, self.owner):
            self.client.force_login(actor)
            response = self.client.get(reverse("repairs:list"))
            self.assertEqual(response.status_code, 403 if actor.is_staff else 200)
            if actor.is_staff:
                continue
            if actor == self.owner:
                self.assertContains(response, reverse("repairs:create"))
            else:
                self.assertNotContains(response, reverse("repairs:create"))
                self.assertNotContains(response, reverse("backoffice:repair_create"))
                self.assertNotContains(response, "Déclarer une panne")

    def test_client_can_declare_without_forging_owner(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("repairs:create"), {"pc": self.pc.pk, "technician": self.tech.pk, "problem": "heat", "description": "Le PC chauffe.", "technical_notes": "", "client": self.admin.pk})
        repair = RepairRequest.objects.get()
        self.assertRedirects(response, repair.get_absolute_url())
        self.assertEqual(repair.client_id, self.owner.pk)

    def test_client_must_choose_an_active_qualified_technician(self):
        self.client.force_login(self.owner)
        payload = {"pc": self.pc.pk, "problem": "heat", "description": "Panne matérielle", "technical_notes": ""}
        for selected in (None, self.software.pk):
            data = dict(payload)
            if selected is not None:
                data["technician"] = selected
            response = self.client.post(reverse("repairs:create"), data)
            self.assertEqual(response.status_code, 200)
            self.assertIn("technician", response.context["form"].errors)
        with self.assertRaises(ValidationError):
            self.create(technician=self.software)
        self.tech.is_available = False
        self.tech.save(update_fields=["is_available"])
        with self.assertRaises(ValidationError):
            self.create()
        self.assertFalse(RepairRequest.objects.exists())

    def test_technician_choices_follow_problem_and_exclude_staff_profiles(self):
        Technician.objects.create(user=self.admin, skills=["hardware", "software", "network"])
        self.client.force_login(self.owner)
        url = reverse("repairs:technicians")
        response = self.client.get(url, {"problem": "heat"})
        self.assertEqual([item["id"] for item in response.json()["technicians"]], [self.tech.pk])
        response = self.client.get(url, {"problem": "software"})
        self.assertEqual([item["id"] for item in response.json()["technicians"]], [self.software.pk])
        self.assertEqual(self.client.get(url, {"problem": "invalid"}).status_code, 400)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url, {"problem": "heat"}).status_code, 403)

    def test_admin_is_denied_all_repair_routes_and_has_no_navigation(self):
        repair = self.create()
        self.admin.is_superuser = True
        self.admin.save(update_fields=["is_superuser"])
        self.client.force_login(self.admin)
        for prefix, names in [("repairs", ("list", "create", "detail", "assign", "status", "report", "message", "cancel", "photo")),
                              ("backoffice", ("repair_list", "repair_create", "repair_detail", "repair_assign", "repair_status", "repair_report", "repair_message", "repair_cancel", "repair_photo"))]:
            for name in names:
                args = [] if name in ("list", "create", "repair_list", "repair_create") else [repair.pk]
                url = reverse(f"{prefix}:{name}", args=args)
                self.assertEqual(self.client.get(url).status_code, 403, url)
                self.assertEqual(self.client.post(url, {}).status_code, 403, url)
        for path in ("/backoffice/", "/backoffice/comptes/", "/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'href="/reparations/')
            self.assertNotContains(response, 'href="/backoffice/reparations/')
        self.assertEqual(self.client.get("/admin/repairs/repairrequest/").status_code, 403)
        for action in (lambda: save_report(self.admin, repair.pk, self.report()), lambda: change_status(self.admin, repair.pk, "cancelled"), lambda: send_message(self.admin, repair.pk, "Interdit")):
            with self.assertRaises(RepairRequest.DoesNotExist):
                action()

    def test_client_cannot_reassign_after_diagnostic_has_started(self):
        repair = self.diagnose()
        with self.assertRaises(ValidationError):
            assign_technician(self.owner, repair.pk, self.tech.pk)

    def test_no_repair_notifications_or_broken_source_links_for_admin(self):
        repair = self.diagnose()
        change_status(self.tech_user, repair.pk, "waiting", "Pièce attendue")
        self.assertFalse(Notification.objects.filter(repair=repair, recipient__is_staff=True).exists())
        legacy = Notification.objects.create(recipient=self.admin, kind="assignment", title="Ancienne alerte", message="Ancien événement", event_key="old-admin-repair", repair=repair)
        self.assertEqual(legacy.target_url(self.admin), reverse("notifications:list"))
        change_status(self.tech_user, repair.pk, "diagnosis")
        save_report(self.tech_user, repair.pk, self.report(), resolve=True)
        self.client.force_login(self.admin)
        for url in (reverse("backoffice:documents"), reverse("appointments:documents")):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, reverse("backoffice:repair_detail", args=[repair.pk]))
            self.assertNotContains(response, repair.get_absolute_url())

    def test_assignment_requires_the_client_owner_and_matching_skills(self):
        repair = self.create()
        with self.assertRaises(PermissionDenied):
            assign_technician(self.admin, repair.pk, self.tech.pk)
        with self.assertRaises(PermissionDenied):
            assign_technician(self.other, repair.pk, self.tech.pk)
        with self.assertRaises(ValidationError):
            assign_technician(self.owner, repair.pk, self.software.pk)
        form = AssignmentForm(repair=repair)
        self.assertEqual(list(form.fields["technician"].queryset), [self.tech])
        assign_technician(self.owner, repair.pk, self.tech.pk)
        count = repair.notifications.count()
        assign_technician(self.owner, repair.pk, self.tech.pk)
        self.assertEqual(repair.notifications.count(), count)
        repair.refresh_from_db()
        self.assertEqual(repair.status, "assigned")

    def test_unavailable_and_inactive_technicians_are_rejected(self):
        repair = self.create()
        self.tech.is_available = False
        self.tech.save()
        with self.assertRaises(ValidationError):
            assign_technician(self.owner, repair.pk, self.tech.pk)
        self.tech.is_available = True
        self.tech.save()
        self.tech_user.is_active = False
        self.tech_user.save()
        with self.assertRaises(ValidationError):
            assign_technician(self.owner, repair.pk, self.tech.pk)

    def test_only_owner_and_assigned_technician_can_read(self):
        repair = self.diagnose()
        for actor, expected in [(self.owner, 200), (self.tech_user, 200), (self.admin, 403), (self.other, 404), (self.software_user, 404)]:
            self.client.force_login(actor)
            self.assertEqual(self.client.get(repair.get_absolute_url()).status_code, expected)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse("repairs:report", args=[repair.pk]), self.report()).status_code, 403)

    def test_status_transitions_and_waiting_alerts(self):
        repair = self.diagnose()
        with self.assertRaises(ValidationError):
            change_status(self.tech_user, repair.pk, "waiting")
        change_status(self.tech_user, repair.pk, "waiting", "Ventilateur en rupture")
        self.assertEqual(set(Notification.objects.filter(repair=repair, kind="component").values_list("recipient_id", flat=True)), {self.owner.pk, self.tech_user.pk})
        change_status(self.tech_user, repair.pk, "repair")
        with self.assertRaises(ValidationError):
            change_status(self.tech_user, repair.pk, "assigned")
        with self.assertRaises(PermissionDenied):
            change_status(self.owner, repair.pk, "resolved")

    def test_resolution_requires_diagnosis_and_solution_and_rolls_back(self):
        repair = self.diagnose()
        with self.assertRaises(ValidationError):
            save_report(self.tech_user, repair.pk, {"diagnosis": "", "solution": "", "labour_cost": Decimal("9.000")}, resolve=True)
        repair.refresh_from_db()
        self.assertEqual(repair.labour_cost, Decimal("0.000"))
        self.assertEqual(repair.status, "diagnosis")
        self.assertFalse(Invoice.objects.filter(repair=repair).exists())

    def test_resolution_creates_history_and_frozen_pdf_once(self):
        repair = self.diagnose()
        component = SparePart.objects.create(category=Category.objects.get(code="fan"), reference="FAN-TEST", name="Ventilateur test", brand="Dell", unit_price="12.100", stock=3)
        import uuid
        use_component(self.tech_user, component_id=component.pk, quantity=2, repair_id=repair.pk, token=uuid.uuid4())
        save_report(self.tech_user, repair.pk, self.report(), resolve=True)
        invoice = Invoice.objects.get(repair=repair)
        self.assertEqual(invoice.total_amount, Decimal("49.325"))
        repair.refresh_from_db()
        self.assertEqual(repair.status, "resolved")
        self.assertIsNotNone(repair.maintenance_record)
        self.assertIn("Ventilateur test", repair.maintenance_record.description)
        change_status(self.tech_user, repair.pk, "resolved")
        self.assertEqual(Invoice.objects.filter(repair=repair).count(), 1)
        self.pc.name = "PC renommé après clôture"
        self.pc.save()
        self.client.force_login(self.owner)
        for kind in ("report", "invoice"):
            response = self.client.get(reverse("appointments:pdf", args=[invoice.pk, kind]))
            text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(b"".join(response.streaming_content))).pages)
            self.assertIn("49,325 TND", text)
            self.assertIn(repair.reference, text)
            self.assertNotIn("PC renommé après clôture", text)
        self.assertContains(self.client.get(reverse("appointments:documents")), invoice.number)
        self.assertContains(self.client.get(reverse("maintenance:history")), "Rapport PDF")
        self.client.force_login(self.software_user)
        self.assertEqual(self.client.get(reverse("appointments:pdf", args=[invoice.pk, "report"])).status_code, 403)

    def test_closed_request_is_read_only(self):
        repair = self.diagnose()
        save_report(self.tech_user, repair.pk, self.report(), resolve=True)
        for operation in [lambda: save_report(self.tech_user, repair.pk, self.report()), lambda: assign_technician(self.owner, repair.pk, self.tech.pk), lambda: send_message(self.owner, repair.pk, "Encore un message")]:
            with self.assertRaises(ValidationError):
                operation()

    def test_client_cancellation_before_repair_and_notification(self):
        repair = self.diagnose()
        change_status(self.owner, repair.pk, "cancelled")
        repair.refresh_from_db()
        self.assertIsNotNone(repair.closed_at)
        self.assertEqual(repair.status, "cancelled")
        self.assertFalse(Invoice.objects.filter(repair=repair).exists())

    def test_client_cannot_cancel_after_repair_started(self):
        repair = self.diagnose()
        change_status(self.tech_user, repair.pk, "repair")
        with self.assertRaises(PermissionDenied):
            change_status(self.owner, repair.pk, "cancelled")

    def test_messages_are_private_escaped_and_notify_other_participant(self):
        repair = self.diagnose()
        send_message(self.owner, repair.pk, '<script>alert("x")</script>')
        self.assertEqual(repair.messages.count(), 1)
        self.assertEqual(list(Notification.objects.filter(repair=repair, kind="message").values_list("recipient_id", flat=True)), [self.tech_user.pk])
        self.client.force_login(self.tech_user)
        response = self.client.get(repair.get_absolute_url())
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("x")</script>')

    def test_reassignment_revokes_previous_technician_access(self):
        repair = self.create()
        self.software.skills = ["hardware"]
        self.software.save()
        initial = Notification.objects.get(repair=repair, recipient=self.tech_user, kind="assignment")
        assign_technician(self.owner, repair.pk, self.software.pk)
        self.client.force_login(self.tech_user)
        self.assertEqual(self.client.get(repair.get_absolute_url()).status_code, 404)
        initial.refresh_from_db()
        self.assertEqual(initial.target_url(self.tech_user), reverse("repairs:list"))

    def test_photo_is_reencoded_private_and_uuid_named(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            form = RequestForm({"pc": self.pc.pk, "technician": self.tech.pk, "problem": "heat", "description": "Photo du PC"}, {"photo": photo_upload()}, actor=self.owner)
            self.assertTrue(form.is_valid(), form.errors)
            repair = create_request(self.owner, form.cleaned_data)
            self.assertRegex(repair.photo.name, r"^repair-photos/[a-f0-9]{32}\.jpg$")
            with Image.open(repair.photo.path) as image:
                self.assertEqual(image.format, "JPEG")
                self.assertFalse(image.getexif())
            self.client.force_login(self.owner)
            response = self.client.get(reverse("repairs:photo", args=[repair.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "image/jpeg")
            self.assertIn("no-store", response["Cache-Control"])
            self.assertTrue(b"".join(response.streaming_content).startswith(b"\xff\xd8"))
            self.client.force_login(self.other)
            self.assertEqual(self.client.get(reverse("repairs:photo", args=[repair.pk])).status_code, 404)
            self.assertEqual(self.client.get("/media/" + repair.photo.name).status_code, 404)

    def test_invalid_and_oversized_photos_are_rejected(self):
        data = {"pc": self.pc.pk, "problem": "heat", "description": "Panne"}
        for upload in [SimpleUploadedFile("x.svg", b"<svg></svg>", content_type="image/svg+xml"), SimpleUploadedFile("large.jpg", b"x" * (5 * 1024 * 1024 + 1))]:
            form = RequestForm(data, {"photo": upload}, actor=self.owner)
            self.assertFalse(form.is_valid())
            self.assertIn("photo", form.errors)

    def test_failed_creation_removes_photo_and_rolls_back_records(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            form = RequestForm({"pc": self.pc.pk, "technician": self.tech.pk, "problem": "heat", "description": "Panne"}, {"photo": photo_upload()}, actor=self.owner)
            self.assertTrue(form.is_valid())
            with patch("repairs.services.alert", side_effect=RuntimeError("Simulated failure")), self.assertRaises(RuntimeError):
                create_request(self.owner, form.cleaned_data)
            self.assertEqual(RepairRequest.objects.count(), 0)
            self.assertEqual(list(Path(directory).rglob("*.jpg")), [])

    def test_pages_filters_staff_access_and_csrf(self):
        repair = self.create()
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("repairs:list") + "?status=assigned"), repair.reference)
        self.assertNotContains(self.client.get(reverse("repairs:list") + "?status=resolved"), repair.reference)
        for route in ("list", "create", "detail"):
            args = [repair.pk] if route == "detail" else []
            self.assertEqual(self.client.get(reverse(f"repairs:{route}", args=args)).status_code, 200)
        self.assertEqual(self.client.get(reverse("backoffice:repair_list")).status_code, 403)
        self.client.force_login(self.admin)
        for route in ("repair_list", "repair_detail"):
            self.assertEqual(self.client.get(reverse(f"backoffice:{route}", args=[repair.pk] if route == "repair_detail" else [])).status_code, 403)
        self.assertEqual(self.client.get(reverse("backoffice:repair_create")).status_code, 403)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.owner)
        self.assertEqual(secure.post(reverse("repairs:status", args=[repair.pk]), {"status": "cancelled"}).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("repairs:status", args=[repair.pk])).status_code, 405)

    def test_request_protects_pc_deletion(self):
        self.create()
        self.client.force_login(self.owner)
        self.client.post(reverse("maintenance:pc_delete", args=[self.pc.pk]))
        self.assertTrue(type(self.pc).objects.filter(pk=self.pc.pk).exists())

    def test_long_discussion_opens_latest_page_and_keeps_older_messages_accessible(self):
        repair = self.diagnose()
        RepairMessage.objects.bulk_create([RepairMessage(repair=repair, sender=self.owner, body=f"Message confidentiel {index:03d}") for index in range(35)])
        self.client.force_login(self.owner)
        response = self.client.get(repair.get_absolute_url())
        self.assertContains(response, "Message confidentiel 034")
        self.assertNotContains(response, "Message confidentiel 000")
        self.assertContains(response, "Messages précédents")
        self.assertContains(self.client.get(repair.get_absolute_url() + "?messages_page=1"), "Message confidentiel 000")
