import unittest
import os
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from bot import Conversation, load_bot_token, load_crm_client, load_mini_app_url, run
from crm_client import CRMClient, CRMTransferError, NoRedirect, validate_config

TODAY = date(2027, 1, 1)

class TokenConfigTest(unittest.TestCase):
    def test_file_environment_precedence_and_missing(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            env_file = Path(folder) / ".env"
            self.assertIsNone(load_bot_token(env_file))
            env_file.write_text("# local config\nBOT_TOKEN=123:fake_token\n", encoding="utf-8")
            self.assertEqual(load_bot_token(env_file), "123:fake_token")
            with patch.dict(os.environ, {"BOT_TOKEN": "456:other_token"}):
                self.assertEqual(load_bot_token(env_file), "456:other_token")

    def test_invalid_and_duplicate_tokens_are_rejected_without_disclosure(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            env_file = Path(folder) / ".env"
            env_file.write_text("BOT_TOKEN=invalid_secret\n", encoding="utf-8")
            with self.assertRaises(ValueError) as error:
                load_bot_token(env_file)
            self.assertNotIn("invalid_secret", str(error.exception))
            env_file.write_text("BOT_TOKEN=123:one\nBOT_TOKEN=456:two\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "more than one"):
                load_bot_token(env_file)

    def test_mini_app_url_optional_file_and_environment_precedence(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            env_file = Path(folder) / ".env"
            self.assertIsNone(load_mini_app_url(env_file))
            env_file.write_text("BOT_TOKEN=123:fake\nMINI_APP_URL=https://demo.example/site/miniapp.html\n", encoding="utf-8")
            self.assertEqual(load_mini_app_url(env_file), "https://demo.example/site/miniapp.html")
            with patch.dict(os.environ, {"MINI_APP_URL": "https://other.example/app"}):
                self.assertEqual(load_mini_app_url(env_file), "https://other.example/app")

    def test_mini_app_url_rejects_unsafe_or_malformed_values(self):
        for value in ("http://example.com/app", "https://", "https://name:password@example.com/", "https://example.com/#fragment", "https://example.com:999999/app", "https://bad\\example.com/"):
            with self.subTest(value=value), patch.dict(os.environ, {"MINI_APP_URL": value}, clear=True):
                with self.assertRaises(ValueError):
                    load_mini_app_url(Path("nonexistent.env"))

    def test_crm_configuration_is_optional_and_rejects_unsafe_urls(self):
        token = "t" * 43
        self.assertIsNone(validate_config(None, None))
        self.assertEqual(validate_config("http://127.0.0.1:8000/api/", token)[0], "http://127.0.0.1:8000/api/")
        self.assertEqual(validate_config("https://crm.example/api/", token)[0], "https://crm.example/api/")
        for url, value in (("http://crm.example/api/", token), ("https://user:pw@crm.example/", token),
                           ("https://crm.example/?secret=1", token), ("https://crm.example/", "short"),
                           ("https://crm.example/", None), (None, token)):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_config(url, value)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            env_file = Path(folder) / ".env"
            self.assertIsNone(load_crm_client(env_file))
            env_file.write_text(f"CRM_API_URL=https://crm.example/api/\nCRM_API_TOKEN={token}\n", encoding="utf-8")
            self.assertIsInstance(load_crm_client(env_file), CRMClient)

    def test_crm_transport_does_not_follow_redirects_or_expose_failures(self):
        token = "t" * 43
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.example/"))
        client = CRMClient("https://crm.example/api/", token)
        client.opener.open = MagicMock(side_effect=OSError("secret " + token))
        with self.assertRaises(CRMTransferError) as error:
            client.submit({"category_id": "studio"}, "test-key")
        self.assertNotIn(token, str(error.exception))

class ConversationTest(unittest.TestCase):
    def setUp(self):
        self.bot = Conversation()

    def ask(self, user=1, text=None, action=None):
        return self.bot.handle(user, text=text, action=action, today=TODAY)["text"]

    def test_mini_app_button_only_when_url_is_configured(self):
        without = self.bot.handle(1, text="/start", today=TODAY)
        self.assertFalse(any("web_app" in button for row in without["reply_markup"]["inline_keyboard"] for button in row))
        configured = Conversation("https://demo.example/site/miniapp.html")
        for trigger in ({"text": "/start"}, {"action": "home"}):
            result = configured.handle(1, today=TODAY, **trigger)
            button = result["reply_markup"]["inline_keyboard"][0][0]
            self.assertEqual(button["text"], "✨ Open Mini App")
            self.assertEqual(button["web_app"]["url"], "https://demo.example/site/miniapp.html")
            self.assertNotIn("callback_data", button)
        self.assertNotIn("web_app", self.bot.handle(1, text="/start", today=TODAY)["reply_markup"]["inline_keyboard"][0][0])

    @patch("bot.Telegram")
    def test_polling_sends_configured_mini_app_button(self, telegram):
        incoming = {"update_id": 10, "message": {"chat": {"type": "private", "id": 7}, "from": {"id": 7}, "text": "/start"}}
        telegram.return_value.call.side_effect = [[incoming], {"message_id": 1}, KeyboardInterrupt]
        with self.assertRaises(KeyboardInterrupt):
            run("123:fake", "https://demo.example/site/miniapp.html")
        send = telegram.return_value.call.call_args_list[1]
        self.assertEqual(send.args[0], "sendMessage")
        self.assertEqual(send.args[1]["chat_id"], 7)
        self.assertEqual(send.args[1]["reply_markup"]["inline_keyboard"][0][0]["web_app"]["url"], "https://demo.example/site/miniapp.html")

    def test_sample_stay_filters_and_calculates(self):
        self.ask(action="plan")
        self.ask(text="2027-06-10")
        self.ask(text="2027-06-14")
        self.assertIn("budget", self.ask(action="guests:4"))
        result = self.ask(action="budget:160")
        self.assertIn("€540", result)
        self.assertNotIn("€760", result)
        self.assertNotIn("Garden Studio", result)
        self.assertIn("No live availability", result)

    def test_no_matches_and_any_budget(self):
        self.ask(action="plan")
        self.ask(text="2027-06-10")
        self.ask(text="2027-06-14")
        self.ask(action="guests:6")
        self.assertIn("No sample apartments match", self.ask(action="budget:120"))
        self.assertIn("expired", self.ask(action="budget:any"))
        self.ask(action="plan")
        self.ask(text="2027-06-10")
        self.ask(text="2027-06-14")
        self.ask(action="guests:6")
        self.assertIn("€760", self.ask(action="budget:any"))

    def test_faq_and_resort_navigation(self):
        self.assertIn("Five low-rise", self.ask(action="resort"))
        self.assertIn("Choose a question", self.ask(action="faq"))
        self.assertIn("fictional", self.ask(action="faq:0"))
        self.assertIn("couldn't find", self.ask(action="faq:-1"))
        self.assertIn("couldn't find", self.ask(action="faq:99"))

    def test_calendar_months_and_date_selection(self):
        start = self.bot.handle(1, action="plan", today=TODAY)
        self.assertIn("check-in", start["text"])
        self.assertTrue(any(button["callback_data"] == "month:in:2027-02-01" for row in start["reply_markup"]["inline_keyboard"] for button in row))
        february = self.bot.handle(1, action="month:in:2027-02-01", today=TODAY)
        self.assertTrue(any(button["callback_data"] == "cal:in:2027-02-28" for row in february["reply_markup"]["inline_keyboard"] for button in row))
        checkout = self.bot.handle(1, action="cal:in:2027-02-28", today=TODAY)
        self.assertIn("check-out", checkout["text"])
        self.assertTrue(any(button["callback_data"] == "cal:out:2027-03-01" for row in checkout["reply_markup"]["inline_keyboard"] for button in row))
        self.assertIn("expired", self.ask(action="cal:in:2027-02-28"))
        self.assertIn("How many guests", self.ask(action="cal:out:2027-03-01"))

    def test_invalid_dates_do_not_advance(self):
        self.ask(action="plan")
        self.assertIn("valid date", self.ask(text="2027-02-30"))
        self.assertIn("past", self.ask(text="2026-12-31"))
        self.ask(text="2027-06-10")
        self.assertIn("after check-in", self.ask(text="2027-06-10"))
        self.assertIn("90 nights", self.ask(text="2028-01-01"))
        self.assertIn("How many guests", self.ask(text="2027-06-14"))

    def test_sessions_are_isolated_and_old_buttons_expire(self):
        self.ask(user=1, action="plan")
        self.ask(user=2, action="plan")
        self.ask(user=1, text="2027-06-10")
        self.assertIn("check-out", self.ask(user=2, text="2027-07-01"))
        self.assertIn("expired", self.ask(user=1, action="guests:4"))
        self.assertIn("Welcome", self.ask(user=1, text="/cancel"))
        self.assertIn("Choose an option", self.ask(user=1, text="  "))

    def test_demo_submission_retry_uses_same_key_and_payload(self):
        client = MagicMock()
        client.submit.side_effect = [CRMTransferError("unconfirmed"), "sample-123"]
        client.quotes.return_value = [{"id": "one", "name": "Poolside One Bedroom", "nightly_cents": 13500, "total_cents": 54000}]
        bot = Conversation(crm_client=client)
        def ask(**kwargs):
            return bot.handle(1, today=TODAY, **kwargs)
        ask(action="plan")
        ask(text="2027-06-10")
        ask(text="2027-06-14")
        ask(action="guests:4")
        result = ask(action="budget:160")
        pick = result["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        review = ask(action=pick)
        self.assertIn("No live availability", review["text"])
        send = review["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        self.assertIn("couldn't confirm", ask(action=send)["text"])
        self.assertIn("sample-123", ask(action=send)["text"])
        self.assertEqual(client.submit.call_count, 2)
        self.assertEqual(client.submit.call_args_list[0], client.submit.call_args_list[1])
        payload, request_key = client.submit.call_args_list[0].args
        self.assertEqual(payload, {"nightly_cents": 13500, "category_id": "one", "checkin": "2027-06-10", "checkout": "2027-06-14", "guests": 4})
        self.assertEqual(len(request_key), 36)
        self.assertIn("sample-123", ask(action=send)["text"])
        self.assertEqual(client.submit.call_count, 2)

    def test_demo_submission_rejects_old_buttons_and_unknown_categories(self):
        client = MagicMock()
        client.quotes.return_value = [{"id": "one", "name": "Poolside One Bedroom", "nightly_cents": 13500, "total_cents": 54000}]
        bot = Conversation(crm_client=client)
        def ask(**kwargs):
            return bot.handle(1, today=TODAY, **kwargs)
        ask(action="plan")
        ask(text="2027-06-10")
        ask(text="2027-06-14")
        ask(action="guests:4")
        result = ask(action="budget:160")
        pick = result["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        self.assertIn("expired", ask(action="pick:old:one")["text"])
        self.assertIn("expired", ask(action=pick.replace(":one", ":studio"))["text"])
        review = ask(action=pick)
        send = review["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        ask(action="home")
        self.assertIn("expired", ask(action=send)["text"])
        client.submit.assert_not_called()

class PersistentDraftTest(unittest.TestCase):
    def test_resume_conflict_discard_and_isolation(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from draft_store import DraftStore
        with TemporaryDirectory() as directory:
            store = DraftStore(Path(directory) / "drafts.sqlite3")
            client = MagicMock()
            client.quotes.return_value = [{"id": "one", "name": "Poolside One Bedroom", "nightly_cents": 13500, "total_cents": 54000}]
            bot = Conversation(crm_client=client, draft_store=store)
            def prepare():
                bot.handle(1, action="plan", today=TODAY)
                bot.handle(1, text="2027-06-10", today=TODAY)
                bot.handle(1, text="2027-06-14", today=TODAY)
                bot.handle(1, action="guests:4", today=TODAY)
                result = bot.handle(1, action="budget:160", today=TODAY)
                return bot.handle(1, action=result["reply_markup"]["inline_keyboard"][0][0]["callback_data"], today=TODAY)
            first = prepare()
            self.assertIn("Review", first["text"])
            self.assertIn("unfinished", prepare()["text"])
            self.assertIn("No saved", bot.handle(2, text="/resume")["text"])
            self.assertIn("Resumed", bot.handle(1, text="/resume")["text"])
            confirmation = bot.handle(1, text="/discard")
            action = confirmation["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
            self.assertIn("discarded", bot.handle(1, action=action)["text"])
            self.assertIn("expired", bot.handle(1, action=action)["text"])
            self.assertIn("Review", prepare()["text"])
            client.submit.assert_not_called()

    def test_storage_failure_prevents_send(self):
        client, store = MagicMock(), MagicMock()
        store.save.side_effect = OSError("disk unavailable")
        client.quotes.return_value = [{"id": "one", "name": "Poolside One Bedroom", "nightly_cents": 13500, "total_cents": 54000}]
        bot = Conversation(crm_client=client, draft_store=store)
        for kwargs in ({"action": "plan"}, {"text": "2027-06-10"}, {"text": "2027-06-14"}, {"action": "guests:4"}):
            bot.handle(1, today=TODAY, **kwargs)
        result = bot.handle(1, action="budget:160", today=TODAY)
        pick = result["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        self.assertIn("couldn't save", bot.handle(1, action=pick, today=TODAY)["text"])
        client.submit.assert_not_called()

    def test_arrival_details_survive_restart_and_lock_on_first_send(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from draft_store import DraftStore

        client = MagicMock()
        client.quotes.return_value = [{"id": "one", "name": "Poolside One Bedroom", "nightly_cents": 13500, "total_cents": 54000}]
        client.submit.side_effect = [CRMTransferError("unconfirmed"), "sample-123"]
        with TemporaryDirectory() as directory:
            store = DraftStore(Path(directory) / "drafts.sqlite3")
            bot = Conversation(crm_client=client, draft_store=store)
            for arguments in ({"action": "plan"}, {"text": "2027-06-10"}, {"text": "2027-06-14"}, {"action": "guests:4"}):
                bot.handle(1, today=TODAY, **arguments)
            result = bot.handle(1, action="budget:160", today=TODAY)
            pick = result["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
            bot.handle(1, action=pick, today=TODAY)
            draft_id = store.load(1)["draft_id"]
            for choice in ("children:2", "with_pet:1", "by_car:1"):
                bot.handle(1, action=f"arrival:{draft_id}:{choice}", today=TODAY)
            bot = Conversation(crm_client=client, draft_store=store)
            self.assertIn("Children under 18: 2", bot.handle(1, text="/resume", today=TODAY)["text"])
            self.assertIn("couldn't confirm", bot.handle(1, action=f"send:{draft_id}", today=TODAY)["text"])
            self.assertFalse(store.load(1)["arrival_editable"])
            self.assertIn("closed", bot.handle(1, action=f"arrival:{draft_id}:children:1", today=TODAY)["text"])
            self.assertIn("sample-123", bot.handle(1, action=f"send:{draft_id}", today=TODAY)["text"])
            self.assertEqual(client.submit.call_args_list[0], client.submit.call_args_list[1])
            payload, _ = client.submit.call_args.args
            self.assertEqual((payload["children"], payload["with_pet"], payload["by_car"]), (2, True, True))

if __name__ == "__main__":
    unittest.main()
