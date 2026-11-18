"""Run the guest browser regression against an isolated SQLite database."""
import os
from pathlib import Path
from secrets import token_urlsafe
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from wsgiref.simple_server import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "crm"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from django.db import connections

def check():
    with TemporaryDirectory() as directory:
        settings.DATABASES["default"]["NAME"] = str(Path(directory) / "browser.sqlite3")
        django.setup()
        from django.contrib.auth.models import Group

        call_command("migrate", verbosity=0)
        call_command("seed_demo")
        call_command("setup_demo_roles")
        password = token_urlsafe(24)
        staff = get_user_model().objects.create_user("browser-reception", password=password)
        staff.groups.add(Group.objects.get(name="kinshore_reception"))
        connections.close_all()
        with make_server("127.0.0.1", 0, get_wsgi_application()) as server:
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                env = {**os.environ, "KINSHORE_TEST_URL": f"http://127.0.0.1:{server.server_port}",
                       "KINSHORE_TEST_STAFF": staff.username, "KINSHORE_TEST_PASSWORD": password}
                subprocess.run([sys.executable, str(ROOT / "site/test_guest_route.py")], env=env, check=True)
            finally:
                server.shutdown()
                worker.join()


if __name__ == "__main__":
    check()
