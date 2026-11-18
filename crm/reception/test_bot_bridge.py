"""Exercise the bot and the real Django intake together without external services."""
from datetime import date
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import Client, TestCase

from .models import ApartmentType, DemoSubmission, StayRequest

BOT_PATH = Path(__file__).resolve().parents[2] / "bot"
sys.path.insert(0, str(BOT_PATH))
try:
    spec = importlib.util.spec_from_file_location("kinshore_bot_bridge", BOT_PATH / "bot.py")
    bot_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bot_module)
finally:
    sys.path.remove(str(BOT_PATH))

TOKEN = "t" * 43  # Synthetic test-only credential.

class Response(io.BytesIO):
    def __init__(self, data, status):
        super().__init__(data)
        self.status = status

class DjangoTransport:
    """Call the Django test client while retaining the bot's actual HTTP serialization."""
    def __init__(self):
        self.client = Client(enforce_csrf_checks=True)
        self.calls = []
        self.lose_first_response = True

    def open(self, request, timeout):
        if request.get_method() == "GET":
            with patch("reception.guest.timezone.localdate", return_value=date(2027, 1, 1)):
                result = self.client.get("/api/guest/quotes/?" + urlsplit(request.full_url).query)
            return Response(result.content, result.status_code)
        headers = {key.lower(): value for key, value in request.header_items()}
        self.calls.append((json.loads(request.data), headers["idempotency-key"]))
        result = self.client.post("/api/internal/demo-requests/", request.data, content_type="application/json",
                                  HTTP_AUTHORIZATION=headers["authorization"], HTTP_IDEMPOTENCY_KEY=headers["idempotency-key"])
        if self.lose_first_response:
            self.lose_first_response = False
            raise TimeoutError("Simulated lost response after the server accepted the request")
        return Response(result.content, result.status_code)

class BotCRMBridgeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        actor = get_user_model().objects.create_user(username="bridge_test_user")
        actor.user_permissions.add(Permission.objects.get(content_type__app_label="reception", codename="add_stayrequest"))

    def test_bot_retry_after_lost_response_does_not_duplicate_in_crm(self):
        ApartmentType.objects.filter(code="one").update(nightly_cents=14950)
        transport = DjangoTransport()
        crm_client = bot_module.CRMClient("https://crm.example/api/internal/demo-requests/", TOKEN)
        crm_client.opener = transport
        storage = TemporaryDirectory()
        self.addCleanup(storage.cleanup)
        store = bot_module.DraftStore(Path(storage.name) / "drafts.sqlite3")
        bot = bot_module.Conversation(crm_client=crm_client, draft_store=store)
        def ask(**kwargs):
            return bot.handle(1, today=date(2027, 1, 1), **kwargs)
        with patch.dict(os.environ, {"KINSHORE_CRM_TOKEN": TOKEN, "KINSHORE_CRM_USER": "bridge_test_user"}):
            ask(action="plan")
            ask(text="2027-06-10")
            ask(text="2027-06-14")
            ask(action="guests:4")
            result = ask(action="budget:160")
            self.assertIn("sample total €598", result["text"])
            pick = result["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
            review = ask(action=pick)
            self.assertIn("Sample estimate: €598", review["text"])
            send = review["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
            before = StayRequest.objects.count()
            self.assertIn("couldn't confirm", ask(action=send)["text"])
            self.assertEqual(StayRequest.objects.count(), before + 1)
            bot = bot_module.Conversation(crm_client=crm_client, draft_store=store)
            self.assertIn("Resumed demo request", ask(text="/resume")["text"])
            self.assertIn("Demo request received", ask(action=send)["text"])
            self.assertEqual(StayRequest.objects.count(), before + 1)
            self.assertEqual(DemoSubmission.objects.count(), 1)
            self.assertEqual(transport.calls[0], transport.calls[1])
            self.assertEqual(transport.calls[0][0], {"nightly_cents": 14950, "category_id": "one", "checkin": "2027-06-10", "checkout": "2027-06-14", "guests": 4})
            stay = DemoSubmission.objects.select_related("stay__apartment__category").get().stay
            self.assertEqual(stay.apartment.category.code, "one")
            self.assertEqual(stay.status, "requested")
            self.assertEqual(stay.nightly_cents, 14950)
