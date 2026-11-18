"""Local demo settings; not configured for hosting or real customer data."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = "kinshore-local-demo-only-not-a-deployment-secret"
DEBUG = True
ALLOWED_HOSTS = []
ROOT_URLCONF = "config.urls"
INSTALLED_APPS = ["django.contrib.sessions", "django.contrib.auth", "django.contrib.contenttypes", "reception"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "local-demo.sqlite3"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.contrib.auth.context_processors.auth"]},
}]
LOGIN_URL = "/reception/login/"
LOGIN_REDIRECT_URL = "/reception/"
LOGOUT_REDIRECT_URL = LOGIN_URL
