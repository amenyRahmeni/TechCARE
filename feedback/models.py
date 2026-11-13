from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class Feedback(models.Model):
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="feedbacks")
    technician = models.ForeignKey("appointments.Technician", on_delete=models.PROTECT, related_name="feedbacks")
    appointment = models.OneToOneField("appointments.Appointment", on_delete=models.PROTECT, null=True, blank=True, related_name="feedback")
    repair = models.OneToOneField("repairs.RepairRequest", on_delete=models.PROTECT, null=True, blank=True, related_name="feedback")
    rating = models.PositiveSmallIntegerField("note", validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField("commentaire", max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(condition=(models.Q(appointment__isnull=False, repair__isnull=True) | models.Q(appointment__isnull=True, repair__isnull=False)), name="feedback_exactly_one_source"),
            models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name="feedback_rating_1_to_5"),
        ]

    @property
    def source(self):
        return self.repair if self.repair_id else self.appointment

    def __str__(self):
        return f"{self.rating}/5 · {self.technician}"
