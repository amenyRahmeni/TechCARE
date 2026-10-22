"""Read-only access to the old database, used exclusively by the migration script."""
from .settings import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": f"{(BASE_DIR / 'db.sqlite3').as_uri()}?mode=ro",  # noqa: F405
        "OPTIONS": {"uri": True},
    }
}
