"""
Base Django settings for the Medicine Neuro Life project.
All sensitive values are read from environment variables (see backend/.env.example).
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Vercel sets VERCEL=1 and the deployment hostnames. Its filesystem is read-only except /tmp,
# and nothing runs between requests, so a few defaults change there (see below).
ON_VERCEL = env.bool("VERCEL", default=False)
if ON_VERCEL:
    vercel_hosts = (env("VERCEL_URL", default=""), env("VERCEL_PROJECT_PRODUCTION_URL", default=""))
    ALLOWED_HOSTS += [host for host in vercel_hosts if host]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    # local apps
    "apps.accounts",
    "apps.products",
    "apps.leads",
    "apps.campaigns",
    "apps.followups",
    "apps.notifications",
    "apps.reports",
    "apps.audit",
    "apps.clinical",
    "apps.branding",
    "apps.media_files",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.audit.middleware.RequestContextMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASE_ENGINES = {
    "postgresql": "django.db.backends.postgresql",
    "postgres": "django.db.backends.postgresql",
    "mysql": "common.db.mysql",  # Django's MySQL backend + time zone fallback for shared hosts
    "sqlite": "django.db.backends.sqlite3",
}

if env("DATABASE_URL", default=None):
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    DATABASES = {
        "default": {
            "ENGINE": DATABASE_ENGINES.get(env("DB_TYPE", default="mysql"), "common.db.mysql"),
            "NAME": env("DB_NAME", default="medicine"),
            "USER": env("DB_USER", default="medicine"),
            "PASSWORD": env("DB_PASSWORD", default=env("DB_PASS", default="")),
            "HOST": env("DB_HOST", default="localhost"),
            "PORT": env("DB_PORT", default="3306"),
        },
    }

# Reuse a database connection across requests instead of opening one per request. Shared
# hosts cap connections (Hostinger: 500 per hour per user), which a busy page uses up fast.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

if DATABASES["default"]["ENGINE"] in ("django.db.backends.mysql", "common.db.mysql"):
    # Full Unicode (Hindi, Tamil, emoji) and strict mode, so bad data errors instead of
    # being silently truncated. Servers without time zone tables (shared hosting) are
    # handled by common.db.mysql (see docs/database-mysql.md).
    DATABASES["default"].setdefault("OPTIONS", {}).update(
        {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        }
    )
    DATABASES["default"]["TEST"] = {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Also serve admin/API-docs assets straight from the apps on Vercel, in case collectstatic
# output is missing from the function bundle.
WHITENOISE_USE_FINDERS = ON_VERCEL

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Uploads (product images, photos, documents) are kept in the database by default, so they
# work on serverless hosts with no lasting disk. MEDIA_STORAGE=filesystem uses MEDIA_ROOT.
MEDIA_STORAGE_BACKENDS = {
    "database": "apps.media_files.storage.DatabaseStorage",
    "filesystem": "django.core.files.storage.FileSystemStorage",
}
STORAGES = {
    "default": {"BACKEND": MEDIA_STORAGE_BACKENDS[env("MEDIA_STORAGE", default="database")]},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Django REST Framework ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "common.pagination.StandardResultsPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "common.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "public_lead": "10/hour",
        "register": "20/hour",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Medicine Neuro Life API",
    "DESCRIPTION": "Lead generation and sales CRM API.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# --- CORS ---
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"])

# --- Celery / Redis ---
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

CACHES = {
    "default": {
        "BACKEND": env("CACHE_BACKEND", default="django.core.cache.backends.redis.RedisCache"),
        "LOCATION": REDIS_URL,
    }
}

# --- Email (SMTP) ---
# Without SMTP settings in .env, emails are written as files to tmp/sent_emails/ instead.
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.filebased.EmailBackend")
_EMAIL_DIR = "/tmp/sent_emails" if ON_VERCEL else str(BASE_DIR / "tmp" / "sent_emails")
EMAIL_FILE_PATH = env("EMAIL_FILE_PATH", default=_EMAIL_DIR)
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=20)
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL", default="Medicine Neuro Life <no-reply@medicine.local>"
)
SERVER_EMAIL = env("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)
ADMINS = [("Admin", email) for email in env.list("ADMIN_EMAILS", default=[])]

# --- Patient messaging (email + WhatsApp) ---
# Public URL of the React app, used for links inside messages.
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173").rstrip("/")
# The React app must always be allowed to call the API, even if CORS_ALLOWED_ORIGINS omits it.
CORS_ALLOWED_ORIGINS = [*CORS_ALLOWED_ORIGINS, FRONTEND_URL]
CORS_ALLOWED_ORIGINS = [origin.rstrip("/") for origin in dict.fromkeys(CORS_ALLOWED_ORIGINS)]
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=CORS_ALLOWED_ORIGINS)
SITE_NAME = env("SITE_NAME", default="Medicine Neuro Life")
# "sync" sends inside the request, "thread" sends right after it in the background
# (no Redis needed), "celery" queues a Celery task (production). Vercel stops the function
# when the response is sent, so background threads would be cut off there.
NOTIFICATIONS_DELIVERY = env("NOTIFICATIONS_DELIVERY", default="sync" if ON_VERCEL else "thread")
# Recipients on these domains are never contacted (demo/test data). ".demo" is not a real TLD.
NOTIFICATIONS_SKIP_DOMAINS = env.list(
    "NOTIFICATIONS_SKIP_DOMAINS", default=["medicine.demo", "example.demo", "test.demo"]
)
# WhatsApp: "console" logs messages only; "meta" uses the WhatsApp Business Cloud API.
WHATSAPP_PROVIDER = env("WHATSAPP_PROVIDER", default="console")
WHATSAPP_ACCESS_TOKEN = env("WHATSAPP_ACCESS_TOKEN", default="")
WHATSAPP_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID", default="")
WHATSAPP_API_VERSION = env("WHATSAPP_API_VERSION", default="v20.0")
WHATSAPP_TEMPLATE_LANGUAGE = env("WHATSAPP_TEMPLATE_LANGUAGE", default="en")
WHATSAPP_DEFAULT_COUNTRY_CODE = env("WHATSAPP_DEFAULT_COUNTRY_CODE", default="91")
# Appointment reminders go out this many hours before the consultation.
REMINDER_HOURS_BEFORE = env.int("REMINDER_HOURS_BEFORE", default=24)
# Optional sandbox: when set, WhatsApp only goes to these numbers (digits with country code).
WHATSAPP_TEST_RECIPIENTS = env.list("WHATSAPP_TEST_RECIPIENTS", default=[])

CELERY_BEAT_SCHEDULE = {
    "consultation-reminders": {
        "task": "apps.notifications.tasks.send_consultation_reminders",
        "schedule": 15 * 60,  # every 15 minutes
    },
}

# --- File upload limits ---
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[{levelname}] {asctime} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
