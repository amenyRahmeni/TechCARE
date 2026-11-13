import base64
from datetime import datetime, time, timedelta
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pywebpush import WebPushException

from appointments.models import Appointment, Technician
from appointments.services import book_appointment, cancel_appointment, save_intervention, update_status
from appointments.tests import future_start, make_pc
from maintenance.models import MaintenanceRule, Recommendation
from maintenance.services import refresh_recommendations
from .models import Notification, PushDelivery, PushSubscription
from .push import dispatch_push, validate_subscription
from .services import generate_reminders, notify, notify_component_unavailable, notify_message_received, sync_current_recommendations
from .signals import COOKIE_NAME, COOKIE_SALT

User = get_user_model()


def subscription_payload(suffix="device"):
    key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"endpoint": "https://fcm.googleapis.com/wp/" + suffix, "keys": {"p256dh": base64.urlsafe_b64encode(key).rstrip(b"=").decode(), "auth": base64.urlsafe_b64encode(b"1234567890abcdef").rstrip(b"=").decode()}}


class NotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user("notification_client", password="ClientNotif2026!")
        cls.other = User.objects.create_user("notification_other", password="AutreNotif2026!")
        cls.tech_user = User.objects.create_user("notification_tech", password="TechNotif2026!")
        cls.other_tech_user = User.objects.create_user("notification_tech2", password="TechNotif2026!")
        cls.admin = User.objects.create_superuser("notification_admin", "admin@example.test", "AdminNotif2026!")
        cls.tech = Technician.objects.create(user=cls.tech_user)
        cls.other_tech = Technician.objects.create(user=cls.other_tech_user)
        cls.pc = make_pc(cls.customer)

    def setUp(self):
        self.client.force_login(self.customer)
        self.temp = TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / ".qa")
        self.addCleanup(self.temp.cleanup)
        self.key_path = Path(self.temp.name) / "private.pem"
        private = ec.generate_private_key(ec.SECP256R1())
        self.key_path.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        self.settings = override_settings(WEBPUSH_PRIVATE_KEY=str(self.key_path), WEBPUSH_PUBLIC_KEY="public-key-for-endpoint-tests")
        self.settings.enable()
        self.addCleanup(self.settings.disable)

    def book(self, **changes):
        data = {"pc": self.pc, "technician": self.tech, "starts_at": future_start(), "category": "preventive", "reason": "Contrôle du ventilateur", "description": "Nettoyer le PC."}
        data.update(changes)
        return book_appointment(self.customer, data)

    def message(self, user=None, event="event", **changes):
        data = {"kind": "status", "title": "Une nouvelle prise en charge", "message": "Le diagnostic du PC est en cours.", "event_key": event}
        data.update(changes)
        return notify((user or self.customer).pk, **data)

    def make_subscription(self, user=None, suffix="device"):
        payload = subscription_payload(suffix)
        return PushSubscription.objects.create(user=user or self.customer, **validate_subscription(payload))

    def test_booking_notifies_only_client_and_assigned_technician(self):
        appointment = self.book()
        items = Notification.objects.filter(appointment=appointment)
        self.assertEqual(set(items.values_list("recipient_id", flat=True)), {self.customer.pk, self.tech_user.pk})
        self.assertEqual(items.count(), 2)
        self.assertTrue(items.filter(kind="booking", recipient=self.customer).exists())
        self.assertTrue(items.filter(kind="assignment", recipient=self.tech_user).exists())

    def test_confirmed_and_status_changes_are_idempotent(self):
        appointment = self.book()
        update_status(self.tech_user, appointment.pk, "confirmed")
        update_status(self.tech_user, appointment.pk, "confirmed")
        self.assertEqual(Notification.objects.filter(kind="confirmed").count(), 1)
        update_status(self.tech_user, appointment.pk, "diagnosis")
        update_status(self.tech_user, appointment.pk, "repair")
        self.assertEqual(Notification.objects.filter(kind="status", recipient=self.customer).count(), 2)
        self.assertFalse(Notification.objects.filter(kind="status", recipient=self.tech_user).exists())

    def test_completion_notifies_documents_once_and_preserves_history(self):
        appointment = self.book()
        update_status(self.tech_user, appointment.pk, "confirmed")
        update_status(self.tech_user, appointment.pk, "diagnosis")
        save_intervention(self.tech_user, appointment.pk, {"diagnosis": "Poussière", "solution": "Nettoyage et essais", "labour_cost": "20.125"}, [], complete=True)
        update_status(self.tech_user, appointment.pk, "completed")
        self.assertEqual(Notification.objects.filter(kind="documents", recipient=self.customer).count(), 1)
        self.assertEqual(self.pc.maintenance_records.count(), 1)
        self.assertEqual(Notification.objects.filter(kind="status", appointment=appointment).count(), 2)

    def test_cancel_from_both_services_notifies_participants(self):
        first = self.book()
        cancel_appointment(self.customer, first.pk)
        second = self.book(starts_at=future_start(hour=11))
        update_status(self.tech_user, second.pk, "cancelled")
        self.assertEqual(Notification.objects.filter(kind="cancelled").count(), 4)

    def test_booking_failure_and_transaction_rollback_do_not_leave_notifications(self):
        self.book()
        count = Notification.objects.count()
        with self.assertRaises(ValidationError):
            self.book()
        self.assertEqual(Notification.objects.count(), count)
        with self.assertRaises(ValueError):
            with transaction.atomic():
                self.book(starts_at=future_start(hour=11))
                raise ValueError("rollback")
        self.assertEqual(Notification.objects.count(), count)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_reassignment_notifies_former_and_new_technician_and_client(self):
        appointment = self.book()
        data = {"pc": self.pc, "technician": self.other_tech, "starts_at": future_start(hour=11), "category": "preventive", "reason": appointment.reason, "description": appointment.description}
        book_appointment(self.customer, data, appointment.pk)
        updates = Notification.objects.filter(kind="updated")
        self.assertEqual(set(updates.values_list("recipient_id", flat=True)), {self.customer.pk, self.tech_user.pk, self.other_tech_user.pk})
        former = updates.get(recipient=self.tech_user)
        self.assertEqual(former.target_url(self.tech_user), reverse("appointments:list"))
        book_appointment(self.customer, data, appointment.pk)
        self.assertEqual(Notification.objects.filter(kind="updated").count(), 3)

    def test_recommendation_creation_reactivation_and_deduplication(self):
        rule = MaintenanceRule.objects.create(code="notification-ram", title="Contrôler la RAM", description="Conseil de RAM", criterion="ram_below", threshold=32, priority="high")
        recommendation = Recommendation.objects.get(pc=self.pc, rule=rule)
        refresh_recommendations(self.pc)
        self.assertEqual(Notification.objects.filter(recommendation=recommendation).count(), 1)
        rule.threshold = 8
        rule.save()
        self.assertEqual(Notification.objects.current().filter(recommendation=recommendation).count(), 0)
        rule.threshold = 32
        rule.save()
        self.assertEqual(Notification.objects.filter(recommendation=recommendation).count(), 2)
        self.assertEqual(Notification.objects.current().filter(recommendation=recommendation).count(), 1)

    def test_legacy_active_recommendations_are_imported_once_without_resetting_read(self):
        rule = MaintenanceRule.objects.create(code="legacy-notif", title="RAM", description="Conseil", criterion="ram_below", threshold=32)
        Notification.objects.filter(recommendation__rule=rule).delete()
        sync_current_recommendations()
        item = Notification.objects.get(recommendation__rule=rule)
        item.read_at = timezone.now()
        item.save()
        sync_current_recommendations()
        item.refresh_from_db()
        self.assertIsNotNone(item.read_at)
        self.assertEqual(Notification.objects.filter(recommendation__rule=rule).count(), 1)

    def test_j1_reminder_is_based_on_tunis_calendar_day_and_does_not_repeat(self):
        appointment = self.book()
        update_status(self.tech_user, appointment.pk, "confirmed")
        day_before = timezone.localtime(appointment.starts_at).date() - timedelta(days=1)
        now = timezone.make_aware(datetime.combine(day_before, time(0, 10)))
        self.assertEqual(generate_reminders(now), 2)
        self.assertEqual(generate_reminders(now), 0)
        self.assertEqual(Notification.objects.filter(kind="reminder").count(), 2)
        self.assertEqual(generate_reminders(now - timedelta(days=1)), 0)

    def test_pending_cancelled_and_inactive_accounts_do_not_receive_reminders(self):
        appointment = self.book()
        now = appointment.starts_at - timedelta(days=1)
        self.assertEqual(generate_reminders(now), 0)
        update_status(self.tech_user, appointment.pk, "confirmed")
        self.tech_user.is_active = False
        self.tech_user.save()
        self.assertEqual(generate_reminders(now), 1)
        cancel_appointment(self.customer, appointment.pk)
        self.assertEqual(Notification.objects.current().filter(kind="reminder").count(), 0)

    def test_rescheduling_expires_old_reminders_and_cancels_pending_push(self):
        self.make_subscription()
        appointment = self.book()
        update_status(self.tech_user, appointment.pk, "confirmed")
        generate_reminders(appointment.starts_at - timedelta(days=1))
        data = {"pc": self.pc, "technician": self.tech, "starts_at": future_start(hour=11), "category": "preventive", "reason": appointment.reason, "description": appointment.description}
        book_appointment(self.customer, data, appointment.pk)
        self.assertFalse(Notification.objects.current().filter(kind="reminder").exists())
        self.assertTrue(PushDelivery.objects.filter(notification__kind="reminder", state="cancelled").exists())

    def test_private_inbox_feed_actions_and_post_only_with_csrf(self):
        own = self.message()
        foreign = self.message(self.other, "other")
        for name in ("read", "unread", "visit"):
            self.assertEqual(self.client.post(reverse(f"notifications:{name}", args=[foreign.pk])).status_code, 404)
            self.assertEqual(self.client.get(reverse(f"notifications:{name}", args=[own.pk])).status_code, 405)
        guarded = Client(enforce_csrf_checks=True)
        guarded.force_login(self.customer)
        self.assertEqual(guarded.post(reverse("notifications:read", args=[own.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("notifications:feed")).json()["unread"], 1)
        anonymous = Client()
        self.assertEqual(anonymous.get(reverse("notifications:list")).status_code, 302)
        self.assertEqual(anonymous.get(reverse("notifications:feed")).status_code, 302)

    def test_read_unread_and_read_all_preserve_new_arrivals(self):
        first = self.message()
        self.client.post(reverse("notifications:read", args=[first.pk]))
        self.assertEqual(self.client.get(reverse("notifications:feed")).json()["unread"], 0)
        self.client.post(reverse("notifications:unread", args=[first.pk]))
        second = self.message(event="next")
        self.client.post(reverse("notifications:read_all"), {"through": first.pk})
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNotNone(first.read_at)
        self.assertIsNone(second.read_at)

    def test_feed_bursts_have_a_cursor_without_skipping_rows(self):
        for index in range(45):
            self.message(event=f"burst-{index}")
        cursor, found = 0, []
        for _ in range(3):
            data = self.client.get(reverse("notifications:feed"), {"since": cursor}).json()
            found.extend(item["id"] for item in data["items"])
            cursor = data["latest"]
        self.assertEqual(len(set(found)), 45)
        for bad in ("x", "-1", "9" * 100):
            self.assertEqual(self.client.get(reverse("notifications:feed"), {"since": bad}).status_code, 400)

    def test_filters_expiration_pagination_and_escaped_text(self):
        self.message(title='<script>alert("x")</script>', event="xss", kind="recommendation")
        self.message(event="expired", expires_at=timezone.now() - timedelta(seconds=1))
        for index in range(14):
            self.message(event=f"item-{index}")
        response = self.client.get(reverse("notifications:list"), {"group": "maintenance"})
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("x")</script>')
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        response = self.client.get(reverse("notifications:list"), {"page": 2})
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["counts"]["total"], 15)

    def test_staff_inbox_uses_backoffice_but_is_still_personal(self):
        self.message()
        self.message(self.admin, "admin")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("notifications:list"))
        self.assertTemplateUsed(response, "backoffice/base.html")
        self.assertEqual(response.context["counts"]["total"], 1)

    def test_notification_visit_checks_resource_permissions(self):
        appointment = self.book()
        item = Notification.objects.get(kind="assignment", appointment=appointment)
        self.client.force_login(self.tech_user)
        self.assertRedirects(self.client.post(reverse("notifications:visit", args=[item.pk])), reverse("appointments:detail", args=[appointment.pk]))

    def test_subscription_validates_provider_keys_and_requires_csrf(self):
        valid = subscription_payload()
        url = reverse("notifications:subscribe")
        guarded = Client(enforce_csrf_checks=True)
        guarded.force_login(self.customer)
        self.assertEqual(guarded.post(url, valid, content_type="application/json").status_code, 403)
        for endpoint in ("http://127.0.0.1/private", "https://localhost/internal", "https://169.254.169.254/meta", "https://fcm.googleapis.com.attacker.test/push", "https://user@fcm.googleapis.com/wp/test", "https://fcm.googleapis.com:8080/wp/test"):
            self.assertEqual(self.client.post(url, {**valid, "endpoint": endpoint}, content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post(url, {**valid, "keys": {"p256dh": "invalid", "auth": "invalid"}}, content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post(url, valid, content_type="application/json").status_code, 200)
        self.assertEqual(self.client.post(url, valid, content_type="application/json").status_code, 200)
        self.assertEqual(PushSubscription.objects.count(), 1)

    def test_subscription_cannot_be_hijacked_by_another_account(self):
        payload = subscription_payload()
        self.client.post(reverse("notifications:subscribe"), payload, content_type="application/json")
        stranger = Client()
        stranger.force_login(self.other)
        self.assertEqual(stranger.post(reverse("notifications:subscribe"), payload, content_type="application/json").status_code, 409)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse("notifications:subscribe"), payload, content_type="application/json").status_code, 200)
        self.assertEqual(PushSubscription.objects.get().user_id, self.other.pk)

    def test_logout_deactivates_only_this_browser_and_cancels_queued_push(self):
        payload = subscription_payload()
        self.client.post(reverse("notifications:subscribe"), payload, content_type="application/json")
        other_device = self.make_subscription(suffix="other-device")
        self.message()
        self.client.post(reverse("logout"))
        self.assertFalse(PushSubscription.objects.exclude(pk=other_device.pk).get().is_active)
        other_device.refresh_from_db()
        self.assertTrue(other_device.is_active)
        self.assertEqual(PushDelivery.objects.filter(state="cancelled").count(), 1)
        self.assertEqual(self.client.get(reverse("notifications:push_session")).status_code, 401)

    def test_unsubscribe_is_private_and_push_session_verifies_cookie(self):
        self.client.post(reverse("notifications:subscribe"), subscription_payload(), content_type="application/json")
        self.assertTrue(self.client.get(reverse("notifications:push_session")).json()["active"])
        self.client.post(reverse("notifications:unsubscribe"), {}, content_type="application/json")
        self.assertFalse(self.client.get(reverse("notifications:push_session")).json()["active"])
        self.assertFalse(PushSubscription.objects.get().is_active)

    @patch("pywebpush.webpush")
    def test_push_is_queued_transactionally_and_delivered_once(self, send):
        send.return_value = Mock(status_code=201)
        self.make_subscription()
        self.message()
        self.message()
        self.assertEqual(PushDelivery.objects.count(), 1)
        self.assertEqual(dispatch_push()["sent"], 1)
        self.assertEqual(dispatch_push()["sent"], 0)
        send.assert_called_once()
        payload = json.loads(send.call_args.kwargs["data"])
        self.assertEqual(payload["recipient_id"], self.customer.pk)
        self.assertTrue(payload["url"].startswith("/notifications/"))

    @patch("pywebpush.webpush")
    def test_push_retry_and_expired_endpoint_handling(self, send):
        sub = self.make_subscription()
        self.message()
        send.side_effect = WebPushException("Temporary", response=Mock(status_code=503))
        self.assertEqual(dispatch_push()["failed"], 1)
        delivery = PushDelivery.objects.get()
        self.assertEqual(delivery.state, "pending")
        self.assertGreater(delivery.next_attempt_at, timezone.now())
        delivery.next_attempt_at = timezone.now() - timedelta(seconds=1)
        delivery.save()
        send.side_effect = WebPushException("Gone", response=Mock(status_code=410))
        dispatch_push()
        sub.refresh_from_db()
        delivery.refresh_from_db()
        self.assertFalse(sub.is_active)
        self.assertEqual(delivery.state, "failed")
        self.assertEqual(delivery.last_error, "HTTP 410")

    @patch("pywebpush.webpush")
    def test_push_cancels_stale_recommendations_and_does_not_contact_bad_hosts(self, send):
        sub = self.make_subscription()
        self.message(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(dispatch_push()["cancelled"], 1)
        self.message(event="bad-endpoint")
        sub.endpoint = "https://127.0.0.1/internal"
        sub.save()
        self.assertEqual(dispatch_push()["failed"], 1)
        send.assert_not_called()

    def test_future_module_hooks_target_real_participants_and_deduplicate(self):
        appointment = self.book()
        for _ in range(2):
            notify_message_received(recipient_id=self.customer.pk, sender_id=self.tech_user.pk, appointment=appointment, message_id="message-123")
            notify_component_unavailable(appointment=appointment, component_name="SSD", event_id="shortage-123")
        self.assertEqual(Notification.objects.filter(kind="message").count(), 1)
        self.assertEqual(set(Notification.objects.filter(kind="component").values_list("recipient_id", flat=True)), {self.tech_user.pk, self.admin.pk})
        with self.assertRaises(ValidationError):
            notify_message_received(recipient_id=self.other.pk, sender_id=self.tech_user.pk, appointment=appointment, message_id="bad")

    @patch("notifications.management.commands.run_notifications.close_old_connections")
    def test_worker_once_and_key_setup_preserve_existing_configuration(self, cleanup):
        env = Path(self.temp.name) / ".env"
        env.write_text("MYSQL_PASSWORD=private-existing-password\n", encoding="utf-8")
        original_key = self.key_path.read_bytes()
        with override_settings(BASE_DIR=Path(self.temp.name)):
            call_command("setup_webpush", stdout=StringIO())
            call_command("setup_webpush", stdout=StringIO())
        self.assertEqual(self.key_path.read_bytes(), original_key)
        self.assertIn("MYSQL_PASSWORD=private-existing-password", env.read_text(encoding="utf-8"))
        self.assertIn("WEBPUSH_PUBLIC_KEY", env.read_text(encoding="utf-8"))
        call_command("run_notifications", once=True, stdout=StringIO())
        with self.assertRaises(Exception):
            call_command("run_notifications", interval=1, stdout=StringIO())

    def test_service_worker_is_public_with_root_scope_and_no_cache(self):
        response = Client().get(reverse("notifications:service_worker"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("application/javascript", response["Content-Type"])
        self.assertIn(b'self.addEventListener("push"', b"".join(response.streaming_content))

    def test_late_push_is_rejected_when_alert_is_expired_or_belongs_to_another_user(self):
        self.client.post(reverse("notifications:subscribe"), subscription_payload(), content_type="application/json")
        item = self.message()
        foreign = self.message(self.other, "foreign")
        url = reverse("notifications:push_session")
        self.assertTrue(self.client.get(url, {"notification": item.pk}).json()["active"])
        self.assertFalse(self.client.get(url, {"notification": foreign.pk}).json()["active"])
        item.expires_at = timezone.now() - timedelta(seconds=1)
        item.save()
        self.assertFalse(self.client.get(url, {"notification": item.pk}).json()["active"])
