from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


def validate_past_date(value):
    if value > timezone.localdate():
        raise ValidationError("La date ne peut pas être dans le futur.")


class PC(models.Model):
    class DeviceType(models.TextChoices):
        LAPTOP = "laptop", "Portable"
        DESKTOP = "desktop", "Bureau"

    class StorageType(models.TextChoices):
        SSD = "SSD", "SSD"
        HDD = "HDD", "HDD"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pcs", verbose_name="propriétaire")
    name = models.CharField("nom du PC", max_length=80)
    brand = models.CharField("marque", max_length=60)
    model = models.CharField("modèle", max_length=100)
    device_type = models.CharField("type", max_length=10, choices=DeviceType.choices, default=DeviceType.LAPTOP)
    serial_number = models.CharField("numéro de série", max_length=100, blank=True, null=True, default=None, db_collation="utf8mb4_bin")
    operating_system = models.CharField("système d’exploitation", max_length=80)
    processor = models.CharField("processeur", max_length=120, blank=True)
    ram_gb = models.PositiveIntegerField("mémoire RAM (Go)", validators=[MinValueValidator(1), MaxValueValidator(512)])
    storage_gb = models.PositiveIntegerField("stockage (Go)", validators=[MinValueValidator(1), MaxValueValidator(32768)])
    storage_type = models.CharField("type de stockage", max_length=3, choices=StorageType.choices, default=StorageType.SSD)
    purchased_on = models.DateField("date d’achat", null=True, blank=True, validators=[validate_past_date])
    notes = models.TextField("notes", blank=True, max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "ordinateur"
        constraints = [models.UniqueConstraint(fields=["owner", "serial_number"], name="unique_owner_pc_serial")]

    def save(self, *args, **kwargs):
        # MySQL permits multiple NULLs in a unique index, but only one empty string.
        self.serial_number = (self.serial_number or "").strip() or None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("maintenance:pc_detail", args=[self.pk])

    @property
    def last_maintenance(self):
        records = list(self.maintenance_records.all())
        return max((record.completed_on for record in records), default=None)


class MaintenanceRecord(models.Model):
    class Kind(models.TextChoices):
        PREVENTIVE = "preventive", "Entretien préventif"
        REPAIR = "repair", "Réparation"
        UPGRADE = "upgrade", "Mise à niveau"

    pc = models.ForeignKey(PC, on_delete=models.CASCADE, related_name="maintenance_records", verbose_name="ordinateur")
    title = models.CharField("intitulé", max_length=150)
    kind = models.CharField("type", max_length=12, choices=Kind.choices, default=Kind.PREVENTIVE)
    description = models.TextField("compte rendu", max_length=4000)
    completed_on = models.DateField("date de réalisation", validators=[validate_past_date])
    technician = models.CharField("technicien", max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-completed_on", "-pk"]
        verbose_name = "historique de maintenance"
        verbose_name_plural = "historiques de maintenance"

    def __str__(self):
        return f"{self.pc} — {self.title}"

    def clean(self):
        super().clean()
        if self.pc_id and self.completed_on and self.pc.purchased_on and self.completed_on < self.pc.purchased_on:
            raise ValidationError({"completed_on": "La maintenance ne peut pas précéder l’achat du PC."})


class MaintenanceRule(models.Model):
    class Criterion(models.TextChoices):
        RAM = "ram_below", "RAM inférieure au seuil (Go)"
        STORAGE = "storage_below", "Stockage inférieur au seuil (Go)"
        HDD = "hdd", "Disque de type HDD"
        OVERDUE = "maintenance_overdue", "Délai depuis le dernier entretien (jours)"

    class Priority(models.TextChoices):
        HIGH = "high", "Prioritaire"
        MEDIUM = "medium", "À prévoir"
        LOW = "low", "Conseil"

    code = models.SlugField("code", unique=True)
    title = models.CharField("titre", max_length=150)
    description = models.TextField("conseil", max_length=1000)
    criterion = models.CharField("critère", max_length=30, choices=Criterion.choices)
    threshold = models.PositiveIntegerField("seuil", default=0, help_text="Go ou jours selon le critère ; 0 pour le type HDD.")
    priority = models.CharField("priorité", max_length=6, choices=Priority.choices, default=Priority.MEDIUM)
    is_active = models.BooleanField("active", default=True)

    class Meta:
        ordering = ["pk"]
        verbose_name = "règle de maintenance"

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.criterion != self.Criterion.HDD and self.threshold < 1:
            raise ValidationError({"threshold": "Le seuil doit être supérieur à zéro pour ce critère."})


class Recommendation(models.Model):
    pc = models.ForeignKey(PC, on_delete=models.CASCADE, related_name="recommendations")
    rule = models.ForeignKey(MaintenanceRule, on_delete=models.CASCADE, related_name="recommendations")
    reason = models.CharField("constat", max_length=300)
    is_active = models.BooleanField("active", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["pc", "rule"], name="unique_pc_recommendation_rule")]
        ordering = ["-updated_at", "pk"]
        verbose_name = "recommandation"

    def __str__(self):
        return f"{self.pc} — {self.rule.title}"
