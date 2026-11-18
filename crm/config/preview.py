"""Settings for the private VPS preview reached through an SSH tunnel."""
import os

from .settings import *  # noqa: F403
from .settings import MIDDLEWARE as LOCAL_MIDDLEWARE

DEBUG = False
SECRET_KEY = os.environ["KINSHORE_SECRET_KEY"]
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "/data/kinshore.sqlite3"}}
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    *LOCAL_MIDDLEWARE,
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_NAME = "kinshore_preview_session"
CSRF_COOKIE_NAME = "kinshore_preview_csrf"
