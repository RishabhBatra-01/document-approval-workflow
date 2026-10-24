"""Django settings. All secrets come from the environment; none are defaulted."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def required_env(name: str) -> str:
    """Fail loudly at startup rather than misbehaving at request time."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable {name}. "
            f"Copy backend/.env.example to backend/.env and fill it in."
        )
    return value


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = required_env("DJANGO_SECRET_KEY")
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")

INSTALLED_APPS = [
    # No django.contrib.contenttypes: it exists to let other Django features
    # refer to "any model", which nothing here does. Including it creates a
    # django_content_type table that would never be read.
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "accounts",
    "submissions",
]

# No session or CSRF middleware: this API is stateless and authenticates with a
# Bearer token on every request. There is no cookie to forge, so there is
# nothing for CSRF protection to defend.
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = []

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": required_env("DB_HOST"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "NAME": required_env("DB_NAME"),
        "USER": required_env("DB_USER"),
        # Held only in memory from the environment. Never logged, never built
        # into a URL (the password may contain characters that need escaping).
        "PASSWORD": required_env("DB_PASSWORD"),
        "OPTIONS": {"sslmode": os.environ.get("DB_SSLMODE", "require")},
        # Measured: opening a new connection to the Seoul pooler costs ~950ms
        # (TCP plus TLS handshake across the Pacific), while a query on an
        # already-open connection costs ~156ms. At CONN_MAX_AGE=0 every single
        # request paid that handshake.
        #
        # Reused for 10 minutes instead, with a health check so a connection
        # the pooler has dropped is replaced rather than erroring. Each worker
        # holds one pooler slot, which two gunicorn workers can afford.
        "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "600")),
        "CONN_HEALTH_CHECKS": True,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["accounts.authentication.SupabaseTokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "config.errors.api_exception_handler",
    "UNAUTHENTICATED_USER": None,
}

# Precise origins only. A wildcard would be an access-control hole, not a fix.
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
CORS_ALLOW_HEADERS = ["authorization", "content-type"]

SUPABASE_URL = required_env("SUPABASE_URL")
SUPABASE_SECRET_KEY = required_env("SUPABASE_SECRET_KEY")
SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "submissions")
SUPABASE_SIGNED_URL_TTL = int(os.environ.get("SUPABASE_SIGNED_URL_TTL", "300"))

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_TITLE_LENGTH = 150
MAX_NOTE_LENGTH = 2000

# Reject oversized uploads before they are buffered to disk.
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_BYTES + 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_BYTES + 1024

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True
STATIC_URL = "static/"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{levelname} {name} {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
