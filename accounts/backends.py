from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = (username or kwargs.get("email") or "").strip()
        if not identifier or password is None:
            return None
        User = get_user_model()
        candidates = list(User.objects.filter(Q(email__iexact=identifier) | Q(username__iexact=identifier)).distinct()[:2])
        # Fail closed if legacy accounts have ambiguous identifiers.
        if len(candidates) != 1:
            User().set_password(password)
            return None
        user = candidates[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
