import uuid

from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class FailureModel(models.Model):
    class Origin(models.TextChoices):
        SIMULATED = "simulated", "Données simulées"
        REAL = "real", "Historique fourni"

    version = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    origin = models.CharField("origine des données", max_length=12, choices=Origin.choices)
    algorithm = models.CharField(max_length=50, default="Random Forest")
    schema_version = models.PositiveSmallIntegerField(default=1)
    dataset_digest = models.CharField(max_length=64)
    sample_count = models.PositiveIntegerField()
    train_count = models.PositiveIntegerField()
    test_count = models.PositiveIntegerField()
    metrics = models.JSONField()
    feature_importances = models.JSONField()
    feature_bounds = models.JSONField()
    forest = models.JSONField()
    trained_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    trained_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-pk"]
        verbose_name = "modèle de prédiction"

    @property
    def is_demo(self):
        return self.origin == self.Origin.SIMULATED

    @property
    def short_version(self):
        return str(self.version).split("-")[0].upper()

    def __str__(self):
        return f"Random Forest {self.short_version} · {self.get_origin_display()}"


class FailurePrediction(models.Model):
    class Level(models.TextChoices):
        LOW = "low", "Faible"
        MEDIUM = "medium", "Moyen"
        HIGH = "high", "Élevé"

    pc = models.ForeignKey("maintenance.PC", on_delete=models.CASCADE, related_name="failure_predictions")
    model = models.ForeignKey(FailureModel, on_delete=models.PROTECT, related_name="predictions")
    features = models.JSONField()
    input_fingerprint = models.CharField(max_length=64)
    score = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    level = models.CharField(max_length=6, choices=Level.choices)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["pc", "model", "input_fingerprint"], name="unique_pc_model_prediction_input"),
            models.CheckConstraint(condition=models.Q(score__gte=0, score__lte=1), name="failure_score_valid_range"),
        ]
        verbose_name = "prédiction de panne"

    @property
    def percentage(self):
        return round(self.score * 100)

    def __str__(self):
        return f"{self.pc} · {self.get_level_display()}"
