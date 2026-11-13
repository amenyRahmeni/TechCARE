from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from notifications.models import Notification
from .messaging import send_message
from .models import Appointment, AppointmentMessage, Technician
from .tests import make_pc, future_start


class AppointmentMessagingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("chat_client")
        cls.outsider = User.objects.create_user("chat_outsider")
        cls.tech_user = User.objects.create_user("chat_tech")
        cls.other_tech_user = User.objects.create_user("chat_other_tech")
        cls.admin = User.objects.create_user("chat_admin", is_staff=True)
        cls.technician = Technician.objects.create(user=cls.tech_user)
        Technician.objects.create(user=cls.other_tech_user)
        cls.appointment = Appointment.objects.create(client=cls.owner, technician=cls.technician, pc=make_pc(cls.owner), starts_at=future_start(), reason="Discussion privée")

    def test_client_and_technician_exchange_real_messages_with_notifications(self):
        first = send_message(self.owner, self.appointment.pk, "Bonjour, le PC ne démarre plus.")
        send_message(self.tech_user, self.appointment.pk, "Merci, je vais contrôler l’alimentation.")
        self.assertEqual(AppointmentMessage.objects.count(), 2)
        self.assertEqual(Notification.objects.filter(kind="message").count(), 2)
        self.assertEqual(Notification.objects.get(event_key=f"appointment-message:{first.pk}").recipient, self.tech_user)

    def test_other_client_and_technician_cannot_access_or_send(self):
        for actor in (self.outsider, self.other_tech_user):
            with self.assertRaises(PermissionDenied):
                send_message(actor, self.appointment.pk, "Intrusion")
            self.client.force_login(actor)
            self.assertEqual(self.client.get(self.appointment.get_absolute_url()).status_code, 404)
            self.assertEqual(self.client.post(reverse("appointments:message", args=[self.appointment.pk]), {"body": "Intrusion"}).status_code, 404)

    def test_admin_can_message_both_participants(self):
        send_message(self.admin, self.appointment.pk, "Précision de l’atelier")
        self.assertEqual(set(Notification.objects.values_list("recipient_id", flat=True)), {self.owner.pk, self.tech_user.pk})

    def test_closed_thread_is_readonly(self):
        send_message(self.owner, self.appointment.pk, "Message conservé")
        for status in ("completed", "cancelled"):
            self.appointment.status = status
            self.appointment.save(update_fields=["status"])
            with self.assertRaises(ValidationError):
                send_message(self.owner, self.appointment.pk, "Trop tard")
        self.assertEqual(AppointmentMessage.objects.count(), 1)

    def test_message_validation(self):
        for text in ("  ", "x" * 2001):
            with self.assertRaises(ValidationError):
                send_message(self.owner, self.appointment.pk, text)
        self.assertFalse(AppointmentMessage.objects.exists())

    def test_post_sender_forgery_ignored_and_get_does_not_mutate(self):
        self.client.force_login(self.owner)
        url = reverse("appointments:message", args=[self.appointment.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {"body": "Mon message", "sender": self.admin.pk}).status_code, 302)
        self.assertEqual(AppointmentMessage.objects.get().sender, self.owner)

    def test_thread_pagination_opens_latest_and_escapes_html(self):
        AppointmentMessage.objects.bulk_create([AppointmentMessage(appointment=self.appointment, sender=self.owner, body=f"Message numéro {i}") for i in range(32)])
        send_message(self.owner, self.appointment.pk, "<script>attack()</script>")
        self.client.force_login(self.tech_user)
        response = self.client.get(self.appointment.get_absolute_url())
        self.assertEqual(response.context["thread_page"].number, 2)
        self.assertNotContains(response, "<script>attack()</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_reassigned_technician_loses_thread_access(self):
        send_message(self.owner, self.appointment.pk, "Message avant affectation")
        new = Technician.objects.get(user=self.other_tech_user)
        Appointment.objects.filter(pk=self.appointment.pk).update(technician=new)
        with self.assertRaises(PermissionDenied):
            send_message(self.tech_user, self.appointment.pk, "Ancien technicien")
        self.client.force_login(self.other_tech_user)
        self.assertContains(self.client.get(self.appointment.get_absolute_url()), "Message avant affectation")
