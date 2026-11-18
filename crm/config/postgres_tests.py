"""Run Django tests against a dedicated local PostgreSQL test server."""
import os
from .settings import *

DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql",
                         "NAME": os.getenv("PGDATABASE", "postgres"),
                         "HOST": os.getenv("PGHOST", "127.0.0.1"),
                         "PORT": os.getenv("PGPORT", "5432"),
                         "USER": os.getenv("PGUSER", "postgres")}}
