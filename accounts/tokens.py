from datetime import timedelta
import hashlib
import hmac
import uuid

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone


def signing_key():
    return hmac.new(settings.SECRET_KEY.encode(), b"techcare-jwt-v1", hashlib.sha256).digest()


def password_stamp(user):
    return hmac.new(signing_key(), user.password.encode(), hashlib.sha256).hexdigest()


def issue_token(user):
    now = timezone.now()
    return jwt.encode({"sub": str(user.pk), "iat": now, "exp": now + timedelta(minutes=20),
                       "iss": "techcare", "aud": "techcare-api", "jti": uuid.uuid4().hex,
                       "pwd": password_stamp(user)}, signing_key(), algorithm="HS256")


def token_user(token):
    payload = jwt.decode(token, signing_key(), algorithms=["HS256"], issuer="techcare", audience="techcare-api",
                         options={"require": ["sub", "iat", "exp", "iss", "aud", "jti", "pwd"]})
    subject = payload["sub"]
    if not subject.isdigit() or len(subject) > 18:
        raise jwt.InvalidTokenError()
    user = get_user_model().objects.filter(pk=int(subject), is_active=True).first()
    if not user or not hmac.compare_digest(str(payload["pwd"]), password_stamp(user)):
        raise jwt.InvalidTokenError()
    return user
