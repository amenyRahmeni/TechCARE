from decimal import Decimal
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse


def photo_path(instance, filename):
    return f"repair-photos/{uuid.uuid4().hex}.jpg"


class RepairRequest(models.Model):
    class Problem(models.TextChoices):
        BOOT = "boot", "PC ne démarre pas"
        SCREEN = "screen", "Écran noir / affichage"
        SLOW = "slow", "Lenteur"
        HEAT = "heat", "Surchauffe"
        BATTERY = "battery", "Batterie / autonomie"
        STORAGE = "storage", "Stockage"
        MEMORY = "memory", "Mémoire RAM"
        SYSTEM = "system", "Erreur système"
        NETWORK = "network", "Réseau / connexion"
        SOFTWARE = "software", "Logiciel"
        VIRUS = "virus", "Virus / sécurité"
        OTHER = "other", "Autre panne matérielle"

    class Status(models.TextChoices):
        SENT = "sent", "Envoyée"
        ASSIGNED = "assigned", "Affectée"
        DIAGNOSIS = "diagnosis", "En diagnostic"
        REPAIR = "repair", "En réparation"
        WAITING = "waiting", "En attente de pièce"
        RESOLVED = "resolved", "Résolue"
        CANCELLED = "cancelled", "Annulée"

    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="repair_requests")
    pc = models.ForeignKey("maintenance.PC", on_delete=models.PROTECT, related_name="repair_requests", verbose_name="ordinateur")
    technician = models.ForeignKey("appointments.Technician", on_delete=models.PROTECT, null=True, blank=True, related_name="repair_requests")
    problem = models.CharField("type de problème", max_length=12, choices=Problem.choices)
    description = models.TextField("description de la panne", max_length=4000)
    technical_notes = models.TextField("informations techniques complémentaires", max_length=2000, blank=True)
    photo = models.ImageField("photo", upload_to=photo_path, blank=True)
    status = models.CharField("statut", max_length=12, choices=Status.choices, default=Status.SENT, db_index=True)
    diagnosis = models.TextField("diagnostic", max_length=4000, blank=True)
    solution = models.TextField("solution / travaux réalisés", max_length=4000, blank=True)
    waiting_reason = models.CharField("pièce attendue / motif d’attente", max_length=250, blank=True)
    labour_cost = models.DecimalField("main-d’œuvre (TND)", max_digits=10, decimal_places=3, default=Decimal("0.000"), validators=[MinValueValidator(0)])
    maintenance_record = models.OneToOneField("maintenance.MaintenanceRecord", on_delete=models.PROTECT, null=True, blank=True, related_name="repair_request")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "demande de réparation"
        indexes = [models.Index(fields=["technician", "status"], name="repair_assignment_idx")]

    def __str__(self):
        return f"{self.reference} · {self.pc}"

    @property
    def reference(self):
        return f"REP-{self.pk:05d}" if self.pk else "Nouvelle demande"

    @property
    def is_closed(self):
        return self.status in (self.Status.RESOLVED, self.Status.CANCELLED)

    @property
    def required_skill(self):
        return {"system": "software", "software": "software", "virus": "software", "slow": "software", "network": "network"}.get(self.problem, "hardware")

    @property
    def parts_total(self):
        return sum((line.total for line in self.component_usages.filter(returned_at__isnull=True)), Decimal("0.000"))

    @property
    def total_amount(self):
        return self.labour_cost + self.parts_total

    def get_absolute_url(self):
        return reverse("repairs:detail", args=[self.pk])


class RepairEvent(models.Model):
    repair = models.ForeignKey(RepairRequest, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    title = models.CharField(max_length=150)
    detail = models.CharField(max_length=700, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "événement de réparation"


class RepairMessage(models.Model):
    repair = models.ForeignKey(RepairRequest, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField("message", max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "message de réparation"
