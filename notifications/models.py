import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class NotificationQuerySet(models.QuerySet):
    def current(self):
        return self.filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now()))


class NotificationCampaign(models.Model):
    class Audience(models.TextChoices):
        ALL = "all", "Clients et techniciens"
        CLIENTS = "clients", "Tous les clients"
        TECHNICIANS = "technicians", "Tous les techniciens"
        SELECTED = "selected", "Destinataires précis"

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="notification_campaigns")
    audience = models.CharField("public", max_length=15, choices=Audience.choices)
    title = models.CharField("titre", max_length=150)
    message = models.CharField("message", max_length=700)
    level = models.CharField("priorité", max_length=10, choices=[("info", "Information"), ("success", "Bonne nouvelle"), ("warning", "À surveiller")])
    payload_hash = models.CharField(max_length=64, editable=False)
    recipient_count = models.PositiveIntegerField("destinataires à l’envoi", default=0)
    sent_at = models.DateTimeField("envoyée le", auto_now_add=True)
    withdrawn_at = models.DateTimeField("retirée le", null=True, blank=True)
    withdrawn_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="withdrawn_notification_campaigns")

    class Meta:
        ordering = ["-sent_at", "-pk"]
        verbose_name = "diffusion de notification"
        verbose_name_plural = "diffusions de notifications"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("backoffice:notification_detail", args=[self.pk])


class Notification(models.Model):
    class Kind(models.TextChoices):
        BOOKING = "booking", "Rendez-vous créé"
        ASSIGNMENT = "assignment", "Affectation"
        CONFIRMED = "confirmed", "Confirmation"
        UPDATED = "updated", "Modification"
        CANCELLED = "cancelled", "Annulation"
        REMINDER = "reminder", "Rappel de rendez-vous"
        STATUS = "status", "Suivi d’intervention"
        RECOMMENDATION = "recommendation", "Maintenance"
        DOCUMENTS = "documents", "Documents disponibles"
        MESSAGE = "message", "Message reçu"
        FEEDBACK = "feedback", "Évaluation reçue"
        COMPONENT = "component", "Pièce indisponible"
        ANNOUNCEMENT = "announcement", "Message de l’administration"

    class Level(models.TextChoices):
        INFO = "info", "Information"
        SUCCESS = "success", "Bonne nouvelle"
        WARNING = "warning", "À surveiller"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications", verbose_name="destinataire")
    kind = models.CharField("type", max_length=20, choices=Kind.choices)
    level = models.CharField("priorité", max_length=10, choices=Level.choices, default=Level.INFO)
    title = models.CharField("titre", max_length=150)
    message = models.CharField("message", max_length=700)
    event_key = models.CharField("clé de l’événement", max_length=160)
    appointment = models.ForeignKey("appointments.Appointment", on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications")
    recommendation = models.ForeignKey("maintenance.Recommendation", on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications")
    repair = models.ForeignKey("repairs.RepairRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications")
    component = models.ForeignKey("inventory.SparePart", on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications")
    campaign = models.ForeignKey(NotificationCampaign, on_delete=models.PROTECT, null=True, blank=True, related_name="notifications")
    read_at = models.DateTimeField("lu le", null=True, blank=True)
    expires_at = models.DateTimeField("expiration", null=True, blank=True)
    created_at = models.DateTimeField("créé le", auto_now_add=True)
    objects = NotificationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "notification"
        constraints = [models.UniqueConstraint(fields=["recipient", "event_key"], name="unique_recipient_notification_event")]
        indexes = [models.Index(fields=["recipient", "read_at", "-created_at"], name="notification_inbox_idx")]

    def __str__(self):
        return self.title

    @property
    def icon(self):
        return {self.Kind.ANNOUNCEMENT: "bell", self.Kind.FEEDBACK: "sparkles", self.Kind.RECOMMENDATION: "sparkles", self.Kind.DOCUMENTS: "file", self.Kind.STATUS: "tool", self.Kind.COMPONENT: "alert", self.Kind.MESSAGE: "message", self.Kind.REMINDER: "clock"}.get(self.kind, "calendar")

    def target_url(self, user):
        from appointments.permissions import can_use_client_features, is_technician_workspace
        if user.pk != self.recipient_id:
            return reverse("notifications:list")
        if self.kind == self.Kind.FEEDBACK:
            return reverse("feedback:list")
        if self.repair_id:
            repair = self.repair
            if user.is_staff:
                return reverse("notifications:list")
            if (can_use_client_features(user) and user.pk == repair.client_id) or (repair.technician_id and repair.technician.user_id == user.pk):
                return repair.get_absolute_url()
            return reverse("repairs:list")
        if self.component_id:
            return self.component.get_absolute_url()
        if self.appointment_id:
            appointment = self.appointment
            if user.is_staff:
                return reverse("backoffice:detail", args=[appointment.pk])
            if user.pk == appointment.technician.user_id or (can_use_client_features(user) and user.pk == appointment.client_id):
                return reverse("appointments:detail", args=[appointment.pk])
            return reverse("appointments:list")
        if self.recommendation_id:
            pc = self.recommendation.pc
            if user.is_staff:
                return reverse("backoffice:pc_detail", args=[pc.pk])
            if is_technician_workspace(user):
                from maintenance.permissions import viewable_pcs
                return pc.get_absolute_url() if viewable_pcs(user).filter(pk=pc.pk).exists() else reverse("appointments:list")
            if pc.owner_id == user.pk:
                return reverse("maintenance:pc_detail", args=[pc.pk])
        return reverse("notifications:list")


class PushSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.TextField()
    endpoint_hash = models.CharField(max_length=64, unique=True)
    p256dh = models.CharField(max_length=100)
    auth = models.CharField(max_length=30)
    browser_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "abonnement navigateur"

    def __str__(self):
        return f"Navigateur de {self.user}"


class PushDelivery(models.Model):
    class State(models.TextChoices):
        PENDING = "pending", "En attente"
        PROCESSING = "processing", "En cours"
        SENT = "sent", "Envoyé"
        FAILED = "failed", "Échec"
        CANCELLED = "cancelled", "Annulé"

    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="push_deliveries")
    subscription = models.ForeignKey(PushSubscription, on_delete=models.CASCADE, related_name="deliveries")
    state = models.CharField(max_length=12, choices=State.choices, default=State.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    locked_at = models.DateTimeField(null=True, blank=True)
    lease = models.UUIDField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "envoi push"
        constraints = [models.UniqueConstraint(fields=["notification", "subscription"], name="unique_notification_push_subscription")]
        indexes = [models.Index(fields=["state", "next_attempt_at"], name="push_outbox_idx")]
