from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from appointments.models import Appointment, Technician
from appointments.tests import future_start, make_pc
from notifications.models import Notification
from repairs.models import RepairRequest
from .models import Feedback
from .services import submit_feedback, technician_scores


class FeedbackTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("review_client", password="ReviewTest2026!")
        cls.other = User.objects.create_user("other_review", password="ReviewTest2026!")
        cls.tech_user = User.objects.create_user("review_technician", password="ReviewTest2026!")
        cls.other_tech_user = User.objects.create_user("review_other_tech", password="ReviewTest2026!")
        cls.staff = User.objects.create_user("review_admin", is_staff=True)
        cls.tech = Technician.objects.create(user=cls.tech_user)
        cls.other_tech = Technician.objects.create(user=cls.other_tech_user)
        cls.pc = make_pc(cls.owner)
        cls.appointment = Appointment.objects.create(client=cls.owner, technician=cls.tech, pc=cls.pc, starts_at=future_start(), status="completed", reason="Réparation terminée")
        cls.repair = RepairRequest.objects.create(client=cls.owner, technician=cls.tech, pc=cls.pc, problem="heat", description="Chauffe du PC", status="resolved")

    def submit(self, **changes):
        data = {"actor": self.owner, "kind": "appointment", "source_id": self.appointment.pk, "rating": 5, "comment": "Prise en charge claire et rapide."}
        data.update(changes)
        return submit_feedback(**data)

    def test_client_rates_appointment_and_notifies_only_technician(self):
        review = self.submit()
        self.assertEqual(review.client, self.owner)
        self.assertEqual(review.technician, self.tech)
        notice = Notification.objects.get(kind="feedback")
        self.assertEqual(notice.recipient, self.tech_user)
        self.assertEqual(notice.target_url(self.tech_user), reverse("feedback:list"))

    def test_repair_review_and_cross_module_average(self):
        self.submit(rating=5)
        self.submit(kind="repair", source_id=self.repair.pk, rating=2)
        self.assertEqual(technician_scores(self.tech), {"average": 3.5, "count": 2})
        self.assertEqual(technician_scores(self.other_tech)["count"], 0)

    def test_pending_repair_cannot_be_rated(self):
        for kind, item in (("appointment", self.appointment), ("repair", self.repair)):
            item.status = "repair"
            item.save(update_fields=["status"])
            with self.assertRaises(ValidationError):
                self.submit(kind=kind, source_id=item.pk)
        self.assertFalse(Feedback.objects.exists())

    def test_cancelled_repair_cannot_be_rated(self):
        self.repair.status = "cancelled"
        self.repair.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            self.submit(kind="repair", source_id=self.repair.pk)

    def test_rating_and_comment_validation(self):
        for value in (0, 6):
            with self.assertRaises(ValidationError):
                self.submit(rating=value)
        for value in ("  ", "x" * 2001):
            with self.assertRaises(ValidationError):
                self.submit(comment=value)
        self.assertFalse(Feedback.objects.exists())

    def test_duplicate_rejected_without_notification_duplicates(self):
        self.submit()
        with self.assertRaises(ValidationError):
            self.submit(rating=1)
        self.assertEqual(Feedback.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(kind="feedback").count(), 1)

    def test_only_owner_can_publish(self):
        for actor in (self.other, self.tech_user, self.other_tech_user, self.staff):
            with self.assertRaises(PermissionDenied):
                self.submit(actor=actor)
        self.assertFalse(Feedback.objects.exists())

    def test_database_rejects_invalid_rating_and_sources(self):
        for changes in ({"rating": 0}, {"repair": self.repair}, {"appointment": None}):
            data = {"client": self.owner, "technician": self.tech, "appointment": self.appointment, "rating": 5, "comment": "Bien"}
            data.update(changes)
            with self.assertRaises(IntegrityError), transaction.atomic():
                Feedback.objects.create(**data)

    def test_overview_role_isolation(self):
        self.submit(comment="Avis confidentiel de ce client")
        for actor, visible in ((self.owner, True), (self.tech_user, True), (self.staff, True), (self.other, False), (self.other_tech_user, False)):
            self.client.force_login(actor)
            response = self.client.get(reverse("feedback:list"))
            self.assertEqual(response.status_code, 200)
            self.assertEqual("Avis confidentiel de ce client" in response.content.decode(), visible)

    def test_form_forged_client_and_technician_are_ignored(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("feedback:create", args=["appointment", self.appointment.pk]), {"rating": 4, "comment": "Tout est clair.", "client": self.other.pk, "technician": self.other_tech.pk})
        self.assertRedirects(response, reverse("feedback:list"))
        review = Feedback.objects.get()
        self.assertEqual((review.client_id, review.technician_id), (self.owner.pk, self.tech.pk))

    def test_technician_and_admin_cannot_open_evaluation_form(self):
        for actor in (self.tech_user, self.staff):
            self.client.force_login(actor)
            self.assertEqual(self.client.get(reverse("feedback:create", args=["appointment", self.appointment.pk])).status_code, 403)

    def test_other_client_cannot_open_evaluation_form(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("feedback:create", args=["appointment", self.appointment.pk])).status_code, 404)

    def test_pending_tasks_and_prompt_on_completed_detail(self):
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("feedback:list")), "Évaluer")
        self.assertContains(self.client.get(self.repair.get_absolute_url()), "Donner mon avis")
        self.assertContains(self.client.get(self.appointment.get_absolute_url()), "Donner mon avis")

    def test_html_is_escaped(self):
        self.submit(comment='<script>alert("x")</script>')
        self.client.force_login(self.owner)
        response = self.client.get(reverse("feedback:list"))
        self.assertNotContains(response, '<script>alert("x")</script>')
        self.assertContains(response, "&lt;script&gt;")

    def test_admin_filters_feedback_and_dashboard_statistics(self):
        self.submit(rating=5)
        self.submit(kind="repair", source_id=self.repair.pk, rating=2)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("backoffice:feedback") + "?rating=2")
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertEqual(self.client.get(reverse("backoffice:dashboard")).context["quality"]["average"], 3.5)
