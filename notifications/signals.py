from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver

from .models import PushDelivery, PushSubscription

COOKIE_NAME = "techcare_push_device"
COOKIE_SALT = "techcare.push.device"


def device_token(request):
    import uuid
    value = request.get_signed_cookie(COOKIE_NAME, salt=COOKIE_SALT, default="")
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        return None


@receiver(user_logged_out)
def deactivate_device_on_logout(sender, request, user, **kwargs):
    if request is not None and user is not None:
        token = device_token(request)
        if token:
            PushSubscription.objects.filter(user=user, browser_token=token).update(is_active=False)
            PushDelivery.objects.filter(subscription__user=user, subscription__browser_token=token, state="pending").update(state="cancelled")
