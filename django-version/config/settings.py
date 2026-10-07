import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "development-only-change-in-production"
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY es obligatorio")
if not DEBUG and len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY debe tener al menos 50 caracteres")
SECRET_KEY_FALLBACKS = [value for value in os.environ.get("DJANGO_SECRET_KEY_FALLBACKS", "").split(",") if value]
ALLOWED_HOSTS = [value.strip() for value in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if value.strip()]
CSRF_TRUSTED_ORIGINS = [value.strip() for value in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if value.strip()]
CSRF_FAILURE_VIEW = "maintenance.views.csrf_failure"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "maintenance",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "maintenance.middleware.JsonCsrfFailureMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = []
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "mesa_mantenimiento"),
        "USER": os.environ.get("POSTGRES_USER", "mesa"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "mesa_local" if DEBUG else ""),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}
if not DEBUG and not DATABASES["default"]["PASSWORD"]:
    raise ImproperlyConfigured("POSTGRES_PASSWORD es obligatorio")
AUTH_USER_MODEL = "maintenance.User"
LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/django-static/"
STATIC_ROOT = BASE_DIR / "collected-static"
STATICFILES_DIRS = [BASE_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_NAME = "mesa_session"
SESSION_COOKIE_AGE = 43200
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_SECURE = os.environ.get("DJANGO_SECURE_COOKIES", "0") == "1"
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
