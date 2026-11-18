"""Production settings for a dedicated, fictional public demo environment."""
import os

from .preview import *  # noqa: F403
from .preview import MIDDLEWARE as PREVIEW_MIDDLEWARE

PUBLIC_DEMO = True
PUBLIC_DEMO_UPSTREAM_IP = os.environ.get("KINSHORE_UPSTREAM_IP", "")
ALLOWED_HOSTS = [os.environ["KINSHORE_DEMO_HOST"]]
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ["POSTGRES_DB"],
    "USER": os.environ["POSTGRES_USER"],
    "PASSWORD": os.environ["POSTGRES_PASSWORD"],
    "HOST": "db",
    "PORT": 5432,
}}
MIDDLEWARE = [
    *PREVIEW_MIDDLEWARE,
    "django.middleware.common.CommonMiddleware",
    "reception.public_demo.PublicDemoMiddleware",
]
if PUBLIC_DEMO_UPSTREAM_IP:
    ALLOWED_HOSTS.append(PUBLIC_DEMO_UPSTREAM_IP)
    MIDDLEWARE.insert(0, "reception.public_demo.PublicDemoUpstreamMiddleware")

APPEND_SLASH = False
SESSION_COOKIE_NAME = "__Host-kinshore_demo_session"
CSRF_COOKIE_NAME = "__Host-kinshore_demo_csrf"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 86400
