from django.conf import settings
from django.db import models


class EmailAddress(models.Model):
    """A unique normalized login address, without replacing Django's User model."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="login_email")
    address = models.EmailField(unique=True, max_length=254)

    def __str__(self):
        return self.address
