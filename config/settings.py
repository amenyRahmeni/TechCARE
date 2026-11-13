import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "local-development-pc-maintenance-only")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,[::1]").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "maintenance.apps.MaintenanceConfig",
    "appointments.apps.AppointmentsConfig",
    "backoffice",
    "notifications.apps.NotificationsConfig",
    "repairs.apps.RepairsConfig",
    "inventory.apps.InventoryConfig",
    "accounts",
    "feedback",
    "support",
    "predictions",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "appointments.context_processors.workspace",
        "notifications.context_processors.inbox",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("MYSQL_DATABASE", "atelier_pc"),
        "USER": os.environ.get("MYSQL_USER", "atelier_pc"),
        "PASSWORD": os.environ.get("MYSQL_PASSWORD", ""),
        "HOST": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "PORT": os.environ.get("MYSQL_PORT", "3306"),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES', default_storage_engine=INNODB",
            "connect_timeout": 10,
        },
        "TEST": {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_0900_ai_ci"},
    }
}
# Hosted MySQL: point to the provider's CA certificate to verify its identity.
if os.environ.get("MYSQL_SSL_CA"):
    DATABASES["default"]["OPTIONS"]["ssl_ca"] = os.environ["MYSQL_SSL_CA"]
    DATABASES["default"]["OPTIONS"]["ssl_verify_cert"] = True
    DATABASES["default"]["OPTIONS"]["ssl_verify_identity"] = True
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
AUTHENTICATION_BACKENDS = ["accounts.backends.EmailOrUsernameBackend"]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Tunis"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = Path(os.environ.get("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))
# Uploads are served exclusively by authenticated views, never by a public media route.
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "maintenance:pc_list"
LOGOUT_REDIRECT_URL = "login"
APPOINTMENT_DURATION_MINUTES = 60
APPOINTMENT_OPEN_HOUR = 9
APPOINTMENT_CLOSE_HOUR = 18
APPOINTMENT_WORKING_DAYS = (0, 1, 2, 3, 4, 5)
WEBPUSH_PRIVATE_KEY = os.environ.get("WEBPUSH_PRIVATE_KEY", str(BASE_DIR / ".private/webpush-private.pem"))
WEBPUSH_PUBLIC_KEY = os.environ.get("WEBPUSH_PUBLIC_KEY", "")
WEBPUSH_SUBJECT = os.environ.get("WEBPUSH_SUBJECT", "https://github.com/amenyRahmeni/TechCARE")
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
