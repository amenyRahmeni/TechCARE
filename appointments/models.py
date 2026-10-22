from datetime import timedelta
from decimal import Decimal
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


def invoice_number():
    return f"FAC-{timezone.localdate().year}-{uuid.uuid4().hex[:10].upper()}"


class Technician(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="technician_profile")
    specialty = models.CharField("spécialité", max_length=120, default="Maintenance informatique")
    is_available = models.BooleanField("accepte des rendez-vous", default=True)

    class Meta:
        verbose_name = "technicien"
        ordering = ["user__first_name", "user__username"]

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Appointment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        CONFIRMED = "confirmed", "Confirmé"
        DIAGNOSIS = "diagnosis", "En diagnostic"
        REPAIR = "repair", "En réparation"
        COMPLETED = "completed", "Terminé"
        CANCELLED = "cancelled", "Annulé"

    class Category(models.TextChoices):
        PREVENTIVE = "preventive", "Entretien préventif"
        HARDWARE = "hardware", "Diagnostic matériel"
        SOFTWARE = "software", "Assistance logicielle"
        UPGRADE = "upgrade", "Mise à niveau"

    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="appointments", verbose_name="client")
    pc = models.ForeignKey("maintenance.PC", on_delete=models.PROTECT, related_name="appointments", verbose_name="ordinateur")
    technician = models.ForeignKey(Technician, on_delete=models.PROTECT, related_name="appointments", verbose_name="technicien")
    starts_at = models.DateTimeField("début", db_index=True)
    category = models.CharField("type de demande", max_length=12, choices=Category.choices, default=Category.PREVENTIVE)
    reason = models.CharField("motif", max_length=150)
    description = models.TextField("précisions", max_length=2000, blank=True)
    status = models.CharField("statut", max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-starts_at", "-pk"]
        verbose_name = "rendez-vous"
        verbose_name_plural = "rendez-vous"

    def __str__(self):
        return f"RDV #{self.pk} · {self.pc}"

    def get_absolute_url(self):
        return reverse("appointments:detail", args=[self.pk])

    @property
    def ends_at(self):
        return self.starts_at + timedelta(minutes=settings.APPOINTMENT_DURATION_MINUTES)

    @property
    def can_modify(self):
        return self.status in (self.Status.PENDING, self.Status.CONFIRMED, self.Status.DIAGNOSIS)

    @property
    def is_closed(self):
        return self.status in (self.Status.COMPLETED, self.Status.CANCELLED)


class BookingSlot(models.Model):
    """Unique indexes enforce reservations even under concurrent MySQL requests."""
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name="booking_slot")
    technician = models.ForeignKey(Technician, on_delete=models.CASCADE)
    pc = models.ForeignKey("maintenance.PC", on_delete=models.CASCADE)
    starts_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["technician", "starts_at"], name="unique_technician_slot"),
            models.UniqueConstraint(fields=["pc", "starts_at"], name="unique_pc_slot"),
        ]


class Intervention(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.PROTECT, related_name="intervention")
    diagnosis = models.TextField("diagnostic", max_length=4000, blank=True)
    solution = models.TextField("travaux réalisés / solution", max_length=4000, blank=True)
    labour_cost = models.DecimalField("main-d’œuvre (TND)", max_digits=10, decimal_places=3, default=Decimal("0.000"), validators=[MinValueValidator(0)])
    maintenance_record = models.OneToOneField("maintenance.MaintenanceRecord", on_delete=models.PROTECT, null=True, blank=True, related_name="intervention")
    completed_at = models.DateTimeField("clôture", null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "intervention"

    def __str__(self):
        return str(self.appointment)

    @property
    def parts_total(self):
        return sum((part.total for part in self.parts.all()), Decimal("0.000"))

    @property
    def total_amount(self):
        return self.labour_cost + self.parts_total


class PartLine(models.Model):
    intervention = models.ForeignKey(Intervention, on_delete=models.CASCADE, related_name="parts")
    name = models.CharField("pièce / prestation", max_length=150)
    quantity = models.PositiveIntegerField("quantité", default=1, validators=[MinValueValidator(1), MaxValueValidator(1000)])
    unit_price = models.DecimalField("prix unitaire (TND)", max_digits=10, decimal_places=3, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ["pk"]

    @property
    def total(self):
        return self.unit_price * self.quantity


class Invoice(models.Model):
    intervention = models.OneToOneField(Intervention, on_delete=models.PROTECT, related_name="invoice")
    number = models.CharField("numéro", max_length=30, unique=True, default=invoice_number, editable=False)
    snapshot = models.JSONField("contenu à la clôture", editable=False)
    total_amount = models.DecimalField("total (TND)", max_digits=15, decimal_places=3, editable=False)
    issued_at = models.DateTimeField("émission", default=timezone.now, editable=False)

    class Meta:
        ordering = ["-issued_at", "-pk"]
        verbose_name = "facture"

    def __str__(self):
        return self.number
