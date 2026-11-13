from django.db import models


class FAQItem(models.Model):
    class Category(models.TextChoices):
        ACCOUNT = "account", "Compte & accès"
        MAINTENANCE = "maintenance", "PC & maintenance"
        REPAIR = "repair", "Pannes & réparations"
        BOOKING = "booking", "Rendez-vous"
        DOCUMENTS = "documents", "Rapports & factures"

    question = models.CharField("question", max_length=250)
    answer = models.TextField("réponse", max_length=6000)
    category = models.CharField("catégorie", max_length=20, choices=Category.choices)
    is_active = models.BooleanField("publiée", default=True)
    position = models.PositiveSmallIntegerField("ordre d’affichage", default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "pk"]
        indexes = [models.Index(fields=["is_active", "category", "position"], name="faq_category_active_idx")]
        verbose_name = "question fréquente"

    def __str__(self):
        return self.question
