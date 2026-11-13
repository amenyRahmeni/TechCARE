import uuid
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Technician
from .campaigns import send_campaign, withdraw_campaign
from .models import Notification, NotificationCampaign, PushDelivery, PushSubscription

User = get_user_model()


class CampaignTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("campaign_admin", is_staff=True)
        cls.other_admin = User.objects.create_superuser("campaign_super", "admin@example.test", "AdminCampaign2026!")
        cls.customer = User.objects.create_user("campaign_client", email="client@example.test", first_name="Client")
        cls.other = User.objects.create_user("campaign_other", email="autre@example.test")
        cls.tech_user = User.objects.create_user("campaign_tech", email="tech@example.test")
        cls.tech = Technician.objects.create(user=cls.tech_user, is_available=False)
        cls.inactive = User.objects.create_user("campaign_inactive", is_active=False)
        cls.inactive_tech = User.objects.create_user("campaign_inactive_tech", is_active=False)
        Technician.objects.create(user=cls.inactive_tech)
        cls.hybrid = Technician.objects.create(user=cls.other_admin)

    def setUp(self):
        self.client.force_login(self.admin)

    def send(self, **changes):
        data = {"token": uuid.uuid4(), "audience": "clients", "title": "Horaires de l’atelier", "message": "Votre atelier vous accueille dès 9 h.", "level": "info"}
        data.update(changes)
        return send_campaign(self.admin, **data)[0]

    def post_data(self, **changes):
        data = {"token": str(uuid.uuid4()), "audience": "clients", "title": "Nouvel horaire", "message": "Ouverture à 9 h.", "level": "warning"}
        data.update(changes)
        return data

    def test_only_admin_can_access_and_send_even_with_direct_service_call(self):
        campaign = self.send()
        urls = [reverse("backoffice:notifications"), reverse("backoffice:notification_create"), campaign.get_absolute_url()]
        for user in (self.customer, self.tech_user):
            self.client.force_login(user)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(reverse("backoffice:notification_withdraw", args=[campaign.pk])).status_code, 403)
            with self.assertRaises(PermissionDenied):
                send_campaign(user, **self.post_data())
            with self.assertRaises(PermissionDenied):
                withdraw_campaign(user, campaign.pk)
        self.client.logout()
        self.assertEqual(self.client.get(urls[0]).status_code, 302)

    def test_client_audience_excludes_technicians_admins_and_inactive_accounts(self):
        campaign = self.send()
        self.assertEqual(campaign.recipient_count, 2)
        self.assertEqual(set(campaign.notifications.values_list("recipient_id", flat=True)), {self.customer.pk, self.other.pk})
        self.assertTrue(campaign.notifications.filter(kind="announcement", level="info").exists())
        self.assertEqual(LogEntry.objects.filter(object_id=str(campaign.pk), change_message__contains="envoyée").count(), 1)

    def test_technicians_and_all_audiences_have_correct_membership(self):
        tech = self.send(audience="technicians")
        self.assertEqual(list(tech.notifications.values_list("recipient_id", flat=True)), [self.tech_user.pk])
        everyone = self.send(audience="all")
        self.assertEqual(set(everyone.notifications.values_list("recipient_id", flat=True)), {self.customer.pk, self.other.pk, self.tech_user.pk})

    def test_selected_recipients_are_deduplicated_and_push_is_queued_only_for_active_subscriptions(self):
        sub = PushSubscription.objects.create(user=self.customer, endpoint="https://fcm.googleapis.com/wp/test", endpoint_hash="1" * 64, p256dh="unused", auth="unused")
        PushSubscription.objects.create(user=self.tech_user, endpoint="https://fcm.googleapis.com/wp/test2", endpoint_hash="2" * 64, p256dh="unused", auth="unused", is_active=False)
        campaign = self.send(audience="selected", selected=[self.customer.pk, self.customer.pk, self.tech_user.pk])
        self.assertEqual(campaign.recipient_count, 2)
        delivery = PushDelivery.objects.get(notification__campaign=campaign)
        self.assertEqual(delivery.subscription, sub)
        self.assertEqual(delivery.state, "pending")

    def test_empty_or_invalid_audience_and_nonrecipient_ids_cannot_send(self):
        for changes in ({"audience": "selected", "selected": []}, {"audience": "selected", "selected": [self.admin.pk]}, {"audience": "selected", "selected": [self.customer.pk, self.inactive.pk]}, {"audience": "unknown"}, {"title": " "}, {"message": "x" * 701}, {"level": "danger"}, {"token": "bad"}):
            with self.assertRaises(ValidationError):
                self.send(**changes)
        self.assertEqual(NotificationCampaign.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_idempotent_retries_preserve_original_audience_snapshot(self):
        token = uuid.uuid4()
        first = self.send(token=token)
        User.objects.create_user("new_client_after_first_send")
        second = self.send(token=token)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.recipient_count, 2)
        self.assertEqual(Notification.objects.count(), 2)
        with self.assertRaises(ValidationError):
            self.send(token=token, title="A different message")

    def test_failed_batch_rolls_back_all_notifications_campaign_and_outbox(self):
        from .services import notify
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("Simulated failure")
            return notify(*args, **kwargs)

        with patch("notifications.campaigns.notify", side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                self.send()
        self.assertEqual(NotificationCampaign.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(PushDelivery.objects.count(), 0)

    def test_post_validates_targets_and_preserves_form_on_error(self):
        url = reverse("backoffice:notification_create")
        for selected in ([], [self.admin.pk], [self.inactive.pk], [999999]):
            response = self.client.post(url, self.post_data(audience="selected", recipients=selected))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
            self.assertEqual(NotificationCampaign.objects.count(), 0)
        response = self.client.post(url, self.post_data(audience="selected", recipients=[self.tech_user.pk]))
        campaign = NotificationCampaign.objects.get()
        self.assertRedirects(response, campaign.get_absolute_url())
        self.assertEqual(list(campaign.notifications.values_list("recipient_id", flat=True)), [self.tech_user.pk])

    def test_post_replay_uses_same_send_and_get_never_sends(self):
        url = reverse("backoffice:notification_create")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(NotificationCampaign.objects.count(), 0)
        data = self.post_data()
        self.client.post(url, data)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(NotificationCampaign.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 2)

    def test_csrf_and_http_methods_protect_actions(self):
        campaign = self.send()
        withdraw_url = reverse("backoffice:notification_withdraw", args=[campaign.pk])
        self.assertEqual(self.client.get(withdraw_url).status_code, 405)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.admin)
        self.assertEqual(secure.post(withdraw_url).status_code, 403)
        self.assertEqual(secure.post(reverse("backoffice:notification_create"), self.post_data()).status_code, 403)
        self.assertEqual(self.client.post(reverse("backoffice:notifications")).status_code, 405)
        self.assertEqual(self.client.post(campaign.get_absolute_url()).status_code, 405)

    def test_read_followup_aggregates_without_changing_recipient_read_state(self):
        first = self.send(audience="all")
        second = self.send()
        self.client.force_login(self.customer)
        item = first.notifications.get(recipient=self.customer)
        self.client.post(reverse("notifications:read", args=[item.pk]))
        self.client.force_login(self.admin)
        response = self.client.get(reverse("backoffice:notifications"))
        self.assertEqual(response.context["stats"]["total"], 2)
        self.assertEqual(response.context["stats"]["recipients"], 5)
        self.assertEqual(response.context["stats"]["read"], 1)
        response = self.client.get(first.get_absolute_url(), {"status": "read"})
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertEqual(response.context["campaign"].read_count, 1)
        self.assertEqual(Notification.objects.filter(read_at__isnull=False).count(), 1)
        self.assertEqual(second.notifications.filter(read_at__isnull=False).count(), 0)

    def test_inbox_and_feed_are_private_and_announcement_filter_works(self):
        campaign = self.send(audience="selected", selected=[self.customer.pk])
        self.client.force_login(self.customer)
        response = self.client.get(reverse("notifications:list"), {"group": "administration"})
        self.assertContains(response, campaign.title)
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertEqual(self.client.get(reverse("notifications:feed")).json()["unread"], 1)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("notifications:feed")).json()["items"], [])
        self.assertEqual(self.client.post(reverse("notifications:read", args=[campaign.notifications.get().pk])).status_code, 404)

    def test_withdraw_hides_only_own_campaign_and_cancels_unsent_push_preserving_read_history(self):
        campaign = self.send()
        other = self.send()
        items = list(campaign.notifications.all())
        items[0].read_at = timezone.now()
        items[0].save(update_fields=["read_at"])
        sub = PushSubscription.objects.create(user=items[0].recipient, endpoint="https://fcm.googleapis.com/wp/x", endpoint_hash="a" * 64, p256dh="unused", auth="unused")
        pending = PushDelivery.objects.create(notification=items[0], subscription=sub)
        another_sub = PushSubscription.objects.create(user=items[1].recipient, endpoint="https://fcm.googleapis.com/wp/y", endpoint_hash="b" * 64, p256dh="unused", auth="unused")
        sent = PushDelivery.objects.create(notification=items[1], subscription=another_sub, state="sent", sent_at=timezone.now())
        self.client.post(reverse("backoffice:notification_withdraw", args=[campaign.pk]))
        self.client.post(reverse("backoffice:notification_withdraw", args=[campaign.pk]))
        campaign.refresh_from_db()
        pending.refresh_from_db()
        sent.refresh_from_db()
        self.assertIsNotNone(campaign.withdrawn_at)
        self.assertEqual(campaign.withdrawn_by, self.admin)
        self.assertEqual(campaign.notifications.current().count(), 0)
        self.assertEqual(campaign.notifications.count(), 2)
        self.assertEqual(campaign.notifications.filter(read_at__isnull=False).count(), 1)
        self.assertEqual(other.notifications.current().count(), 2)
        self.assertEqual(pending.state, "cancelled")
        self.assertEqual(sent.state, "sent")
        self.assertEqual(LogEntry.objects.filter(object_id=str(campaign.pk), change_message__contains="retirée").count(), 1)

    def test_recipient_deletion_keeps_original_delivery_count_and_no_private_events_are_exposed(self):
        campaign = self.send()
        self.other.delete()
        response = self.client.get(campaign.get_absolute_url())
        self.assertEqual(response.context["campaign"].recipient_count, 2)
        self.assertEqual(response.context["campaign"].available_count, 1)
        Notification.objects.create(recipient=self.customer, kind="message", title="Private conversation", message="Private technical details", event_key="private-event")
        self.assertNotContains(self.client.get(reverse("backoffice:notifications")), "Private technical details")
        self.assertNotContains(response, "Private technical details")

    def test_search_filter_and_escaping(self):
        campaign = self.send(title="<script>alert('x')</script>", message="<b>Message</b>")
        self.assertContains(self.client.get(campaign.get_absolute_url()), "&lt;script&gt;")
        self.assertNotContains(self.client.get(campaign.get_absolute_url()), campaign.title)
        response = self.client.get(reverse("backoffice:notifications"), {"q": "missing"})
        self.assertEqual(response.context["page_obj"].paginator.count, 0)
        response = self.client.get(reverse("backoffice:notifications"), {"audience": "technicians"})
        self.assertEqual(response.context["page_obj"].paginator.count, 0)
        withdraw_campaign(self.admin, campaign.pk)
        response = self.client.get(reverse("backoffice:notifications"), {"state": "withdrawn"})
        self.assertEqual(response.context["page_obj"].paginator.count, 1)

    def test_history_pagination_is_stable_with_simultaneous_sends(self):
        campaigns = [self.send(title=f"Message {index}") for index in range(12)]
        NotificationCampaign.objects.update(sent_at=timezone.now())
        first = self.client.get(reverse("backoffice:notifications"))
        second = self.client.get(reverse("backoffice:notifications"), {"page": 2})
        found = [item.pk for response in (first, second) for item in response.context["page_obj"]]
        self.assertEqual(found, sorted([item.pk for item in campaigns], reverse=True))
