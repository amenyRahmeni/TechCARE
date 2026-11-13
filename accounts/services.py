import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import EmailAddress


def claim_email(user):
    """Called inside the transaction saving the user, including admin changes."""
    address = user.email.strip().lower()
    if not address:
        EmailAddress.objects.filter(user=user).delete()
        return
    if get_user_model().objects.filter(email__iexact=address).exclude(pk=user.pk).exists():
        raise ValidationError("Cette adresse e-mail est déjà utilisée.")
    EmailAddress.objects.update_or_create(user=user, defaults={"address": address})


@transaction.atomic
def register(form):
    user = form.save(commit=False)
    # Django keeps an internal username; clients register and sign in by e-mail.
    user.username = f"client_{uuid.uuid4().hex}"
    # Public registration can never elevate privileges, even with forged POST data.
    user.is_active, user.is_staff, user.is_superuser = True, False, False
    user.save()
    claim_email(user)
    return user
