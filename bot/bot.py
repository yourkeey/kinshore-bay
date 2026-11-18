"""Kinshore Bay Telegram bot. Load BOT_TOKEN from the environment or bot/.env."""
import argparse
import calendar
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from catalog import APARTMENTS, CONTENT, apartment
from crm_client import CRMClient, CRMTransferError, validate_config
from draft_store import DraftStore, DraftConflict

DEMO = "Portfolio demo · fictional resort · prices are illustrative. No reservations or payments."
MENU = [[("🏡 Apartments", "apartments"), ("☀️ The resort", "resort")],
        [("📅 Plan a stay", "plan"), ("💬 Questions", "faq")],
        [("ℹ️ About this demo", "about")]]
BUDGETS = {"120": 120, "160": 160, "220": 220, "any": None}
ENV_FILE = Path(__file__).resolve().parent / ".env"

def load_setting(name, env_file=ENV_FILE):
    """Prefer a process environment value over the same key in bot/.env."""
    value = os.environ.get(name, "").strip()
    if not value and env_file.exists():
        try:
            lines = env_file.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError) as exc:
            raise ValueError("Unable to read bot/.env; check its permissions and UTF-8 encoding.") from exc
        entries = [line.split("=", 1)[1].strip().strip("\"'") for line in lines
                   if "=" in line and line.split("=", 1)[0].strip() == name]
        if len(entries) > 1:
            raise ValueError(f"bot/.env has more than one {name} entry.")
        value = entries[0] if entries else ""
    return value or None

def load_bot_token(env_file=ENV_FILE):
    token = load_setting("BOT_TOKEN", env_file)
    if token and not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
        raise ValueError("BOT_TOKEN has an invalid format. Check bot/.env or the environment.")
    return token

def load_mini_app_url(env_file=ENV_FILE):
    value = load_setting("MINI_APP_URL", env_file)
    if not value:
        return None
    try:
        parts = urllib.parse.urlsplit(value)
        if (parts.scheme.lower() != "https" or not parts.hostname or not re.fullmatch(r"[A-Za-z0-9.:-]+", parts.hostname)
                or parts.username is not None or parts.password is not None or parts.fragment
                or "\\" in value or any(ch.isspace() or ord(ch) < 32 for ch in value)):
            raise ValueError
        _ = parts.port  # Reject malformed or out-of-range ports.
    except ValueError:
        raise ValueError("MINI_APP_URL must be an HTTPS URL without credentials or a fragment.") from None
    return value

def load_crm_client(env_file=ENV_FILE):
    url = load_setting("CRM_API_URL", env_file)
    token = load_setting("CRM_API_TOKEN", env_file)
    configured = validate_config(url, token)
    return CRMClient(*configured) if configured else None

def keyboard(rows):
    return {"inline_keyboard": [[{"text": text, "callback_data": value} for text, value in row] for row in rows]}

def reply(text, rows=None):
    result = {"text": text}
    if rows:
        result["reply_markup"] = keyboard(rows)
    return result

def home(mini_app_url=None):
    result = reply(f"Welcome to {CONTENT['brand']['name']} 🌿\n\n{CONTENT['brand']['tagline']} A relaxed family escape by the Mediterranean, imagined for this portfolio project. Explore the apartments or plan a sample stay.\n\n" + DEMO, MENU)
    if mini_app_url:
        result["reply_markup"]["inline_keyboard"].insert(0, [{"text": "✨ Open Mini App", "web_app": {"url": mini_app_url}}])
    return result

def menu_button():
    return [[("← Main menu", "home")]]

def calendar_reply(session, today, month=None):
    """Build an inline calendar; callbacks include the step to reject stale selections."""
    step = session["step"]
    first_allowed = today if step == "checkin" else date.fromisoformat(session["checkin"]) + timedelta(days=1)
    last_allowed = today + timedelta(days=730) if step == "checkin" else date.fromisoformat(session["checkin"]) + timedelta(days=90)
    first_month = first_allowed.replace(day=1)
    month = month or first_month
    tag = "in" if step == "checkin" else "out"
    rows = [[(day, "cal:noop") for day in ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")]]
    for week in calendar.monthcalendar(month.year, month.month):
        row = []
        for number in week:
            current = date(month.year, month.month, number) if number else None
            enabled = current and current >= first_allowed and (last_allowed is None or current <= last_allowed)
            row.append((str(number) if enabled else "·", f"cal:{tag}:{current.isoformat()}" if enabled else "cal:noop"))
        rows.append(row)
    next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    previous_month = (month - timedelta(days=1)).replace(day=1)
    previous = ("‹", f"month:{tag}:{previous_month.isoformat()}") if month > first_month else ("·", "cal:noop")
    following = ("›", f"month:{tag}:{next_month.isoformat()}") if last_allowed is None or next_month <= last_allowed else ("·", "cal:noop")
    rows.append([previous, (f"{calendar.month_name[month.month]} {month.year}", "cal:noop"), following])
    rows += menu_button()
    text = "Choose your check-in date 📅\nDates available up to two years ahead." if step == "checkin" else f"Check-in: {session['checkin']}\n\nNow choose your check-out date 📅\nUp to 90 nights."
    return reply(text + "\n\nDemo only · no reservation.", rows)

def select_date(session, chosen, today):
    if session["step"] == "checkin":
        if chosen < today:
            return reply("Check-in cannot be in the past. Please choose another date.", menu_button())
        if chosen > today + timedelta(days=730):
            return reply("Please choose a check-in date within the next two years.", menu_button())
        session.update(checkin=chosen.isoformat(), step="checkout")
        return calendar_reply(session, today)
    if chosen <= date.fromisoformat(session["checkin"]):
        return reply("Check-out must be after check-in. Please choose another date.", menu_button())
    if (chosen - date.fromisoformat(session["checkin"])).days > 90:
        return reply("For this demo, please choose a stay of 90 nights or fewer.", menu_button())
    session.update(checkout=chosen.isoformat(), step="guests")
    return reply("How many guests are coming?", [[(str(n), f"guests:{n}") for n in (1, 2, 3)], [(str(n), f"guests:{n}") for n in (4, 5, 6)]] + menu_button())

class Conversation:
    def __init__(self, mini_app_url=None, crm_client=None, draft_store=None):
        self.draft_store = draft_store
        self.sessions = {}
        self.mini_app_url = mini_app_url
        self.crm_client = crm_client

    def review(self, session, resumed=False):
        selected = apartment(session["category_id"])
        nights = (date.fromisoformat(session["checkout"]) - date.fromisoformat(session["checkin"])).days
        text = (f"{'Resumed' if resumed else 'Review your'} demo request ✨\n\n{selected['name']}\n"
                f"{session['checkin']} → {session['checkout']} · {nights} night(s) · {session['guests']} guest(s)\n"
                f"Sample estimate: €{session.get('nightly_cents', selected['price'] * 100) * nights / 100:g}\n\n"
                "The demo CRM receives the trip and any arrival details you add. "
                "No live availability, real booking, payment or contact details.")
        buttons = [[("Send demo request", f"send:{session['draft_id']}")]]
        if session.get("arrival_editable"):
            buttons.append([("Children, pet & parking", f"arrival:{session['draft_id']}:open")])
        return reply(text + self.arrival_summary(session), buttons + menu_button())

    @staticmethod
    def arrival_summary(session):
        lines = []
        if "children" in session:
            lines.append(f"Children under 18: {session['children']}")
        if "with_pet" in session:
            lines.append(f"Bringing a pet: {'yes' if session['with_pet'] else 'no'}")
        if "by_car" in session:
            lines.append(f"Arriving by car: {'yes' if session['by_car'] else 'no'}")
        return "\n\n" + "\n".join(lines) if lines else ""

    def arrival_options(self, session):
        prefix = f"arrival:{session['draft_id']}:"
        counts = [(str(n), f"{prefix}children:{n}") for n in range(session["guests"])]
        text = ("Children under 18 count towards your guest total. Reception checks pet requests before confirming. "
                "Covered parking is first come, first served." + self.arrival_summary(session))
        return reply(text, [counts, [
            ("Pet: yes", prefix + "with_pet:1"), ("Pet: no", prefix + "with_pet:0")
        ], [
            ("By car: yes", prefix + "by_car:1"), ("By car: no", prefix + "by_car:0")
        ], [("Back to review", prefix + "review")]])

    def handle(self, user_id, text=None, action=None, today=None):
        today = today or datetime.now(timezone.utc).date()
        session = self.sessions.setdefault(user_id, {})
        command = text.split()[0].split('@')[0] if text and text.strip() else None
        if command == "/resume" or action == "resume":
            if not self.draft_store:
                return reply("No saved demo request is available.", menu_button())
            try:
                saved = self.draft_store.load(user_id)
            except (OSError, ValueError):
                return reply("The saved request is temporarily unavailable. Please try again later.", menu_button())
            if not saved:
                return reply("No saved demo request is available.", menu_button())
            session.clear()
            session.update(saved)
            if saved["step"] == "submitted_demo":
                return reply(f"Demo request received · {saved['reference']}\n\nNo real booking or payment was made.", menu_button())
            return self.review(session, resumed=True)
        if command == "/discard":
            if not self.draft_store:
                return reply("No saved demo request is available.", menu_button())
            try:
                saved = self.draft_store.load(user_id)
            except (OSError, ValueError):
                return reply("The saved request is temporarily unavailable. Please try again later.", menu_button())
            if not saved or saved["step"] != "review_demo":
                return reply("No unfinished demo request is available.", menu_button())
            return reply("Discard the saved request? If delivery was uncertain, it may already exist in the demo CRM. "
                         "A new request could create a duplicate.",
                         [[("Discard saved request", f"discard:{saved['draft_id']}"), ("Keep request", "resume")]] + menu_button())
        if action and action.startswith("discard:"):
            try:
                removed = self.draft_store and self.draft_store.discard(user_id, action[8:])
            except (OSError, ValueError):
                return reply("The saved request is temporarily unavailable. Please try again later.", menu_button())
            if removed:
                session.clear()
                return reply("Saved demo request discarded. This does not delete any request already received by the CRM.", menu_button())
            return reply("This discard confirmation has expired.", menu_button())
        if text and text.strip() and text.split()[0].split('@')[0] in ("/start", "/menu", "/cancel", "/help"):
            session.clear()
            return home(self.mini_app_url)
        if action == "home":
            session.clear()
            return home(self.mini_app_url)
        if action == "apartments":
            session.clear()
            rows = [[(f"{a['name']} · from €{a['price']}/night", "room:" + a["id"])] for a in APARTMENTS]
            return reply("Find your space ☀️\n\nIllustrative nightly rates; no live availability. Choose an apartment:", rows + menu_button())
        if action and action.startswith("room:"):
            a = apartment(action[5:])
            if not a:
                return reply("That apartment is unavailable in this demo.", menu_button())
            return reply(f"{a['name']}\n\n{a['description']}\n{a['size']} m² · up to {a['guests']} guests\nFrom €{a['price']} / night (sample rate)\n\n" + DEMO,
                         [[("📅 Plan a stay", "plan"), ("← Apartments", "apartments")]] + menu_button())
        if action == "resort":
            session.clear()
            features = "\n".join("• " + feature for feature in CONTENT["site"]["resort"]["features"])
            return reply("The resort 🌿\n\n" + CONTENT["site"]["resort"]["body"] + "\n\n" + features + "\n\n" + DEMO,
                         [[("🏡 Explore apartments", "apartments"), ("📅 Plan a stay", "plan")]] + menu_button())
        if action == "faq":
            session.clear()
            questions = CONTENT["site"]["faq"]
            return reply("A few useful answers 💬\n\nChoose a question:",
                         [[(item["question"], f"faq:{i}")] for i, item in enumerate(questions)] + menu_button())
        if action and action.startswith("faq:"):
            index = action[4:]
            questions = CONTENT["site"]["faq"]
            if not index.isascii() or not index.isdigit() or int(index) >= len(questions):
                return reply("Sorry, I couldn't find that answer.", [[("← Questions", "faq")]] + menu_button())
            item = questions[int(index)]
            return reply(f"{item['question']}\n\n{item['answer']}", [[("← Questions", "faq")]] + menu_button())
        if action == "about":
            session.clear()
            return reply(f"{CONTENT['brand']['name']} is a fictional resort created as a portfolio project. Apartments, prices and availability are illustrative. This bot does not accept bookings, payments or personal information.", menu_button())
        if action == "plan":
            session.clear()
            session["step"] = "checkin"
            return calendar_reply(session, today)
        if action == "cal:noop":
            return None
        if action and (action.startswith("cal:") or action.startswith("month:")):
            parts = action.split(":")
            step_tag = {"checkin": "in", "checkout": "out"}.get(session.get("step"))
            if len(parts) != 3 or parts[1] != step_tag or step_tag is None:
                return reply("This calendar has expired. Start a new sample stay.", [[("📅 Plan a stay", "plan")]] + menu_button())
            try:
                selected = date.fromisoformat(parts[2])
                if selected.isoformat() != parts[2]:
                    raise ValueError
            except ValueError:
                return reply("That date is invalid. Start a new sample stay.", [[("📅 Plan a stay", "plan")]] + menu_button())
            if parts[0] == "month":
                first_allowed = today if step_tag == "in" else date.fromisoformat(session["checkin"]) + timedelta(days=1)
                last_allowed = today + timedelta(days=730) if step_tag == "in" else date.fromisoformat(session["checkin"]) + timedelta(days=90)
                if selected.day != 1 or selected < first_allowed.replace(day=1) or (last_allowed and selected > last_allowed):
                    return calendar_reply(session, today)
                return calendar_reply(session, today, selected)
            return select_date(session, selected, today)
        if action and action.startswith("guests:"):
            if session.get("step") != "guests" or action[7:] not in ("1", "2", "3", "4", "5", "6"):
                return reply("This selection has expired. Start a new sample stay.", [[("📅 Plan a stay", "plan")]] + menu_button())
            session.update(guests=int(action[7:]), step="budget")
            return reply("What is your budget per night? 💶\n\nSelect an illustrative maximum, or see all options.",
                         [[("Up to €120", "budget:120"), ("Up to €160", "budget:160")],
                          [("Up to €220", "budget:220"), ("Any budget", "budget:any")]] + menu_button())
        if action and action.startswith("budget:"):
            value = action[7:]
            if session.get("step") != "budget" or value not in BUDGETS:
                return reply("This selection has expired. Start a new sample stay.", [[("📅 Plan a stay", "plan")]] + menu_button())
            guests = session["guests"]
            nights = (date.fromisoformat(session["checkout"]) - date.fromisoformat(session["checkin"])).days
            budget = BUDGETS[value]
            if self.crm_client:
                try:
                    quoted = self.crm_client.quotes(session["checkin"], session["checkout"], guests)
                except CRMTransferError:
                    return reply("Could not check demo inventory. Try your budget again.",
                                 [[("Retry", "budget:" + value)]] + menu_button())
            else:
                quoted = [{**a, "nightly_cents": a["price"] * 100, "total_cents": a["price"] * nights * 100}
                          for a in APARTMENTS if a["guests"] >= guests]
            choices = [a for a in quoted if budget is None or a["nightly_cents"] <= budget * 100]
            lines = [f"{a['name']} · €{a['nightly_cents']/100:g}/night · sample total €{a['total_cents']/100:g}" for a in choices]
            budget_label = f"Up to €{budget}/night" if budget is not None else "Any budget"
            choices_text = "\n\n".join(lines) if lines else "No sample apartments match these guests and this budget. Try a higher budget or start again."
            result = f"Your sample stay ✨\n\n{session['checkin']} → {session['checkout']} · {nights} night(s) · {guests} guest(s)\n{budget_label}\n\n" + choices_text + "\n\nSample estimates only. No live availability, booking or payment."
            if self.crm_client and choices:
                session.update(step="select_demo", allowed={a["id"]: a["nightly_cents"] for a in choices}, draft_id=uuid4().hex[:8])
                choices_rows = [[(f"Request {a['name']}", f"pick:{session['draft_id']}:{a['id']}")] for a in choices]
                result += "\n\nChoose an apartment to review a demo request."
            else:
                session.clear()
                choices_rows = [[(f"View {a['name']}", f"room:{a['id']}")] for a in choices]
            return reply(result, choices_rows + [[("🏡 All apartments", "apartments"), ("↻ Start again", "plan")]] + menu_button())
        if action and action.startswith("pick:"):
            parts = action.split(":")
            if (not self.crm_client or len(parts) != 3 or session.get("step") != "select_demo"
                    or parts[1] != session.get("draft_id") or parts[2] not in session.get("allowed", [])):
                return reply("This selection has expired. Start a new sample stay.", [[("📅 Plan a stay", "plan")]] + menu_button())
            selected = apartment(parts[2])
            if selected is None:
                return reply("That apartment is unavailable in this demo.", menu_button())
            candidate = {key: session[key] for key in ("draft_id", "checkin", "checkout", "guests")}
            candidate.update(step="review_demo", category_id=selected["id"], nightly_cents=session["allowed"][selected["id"]],
                             submission_key=str(uuid4()), arrival_editable=True)
            if self.draft_store:
                try:
                    self.draft_store.save(user_id, candidate)
                except DraftConflict:
                    return reply("You have an unfinished demo request. Resume it or use /discard before starting another.",
                                 [[("Resume request", "resume")]] + menu_button())
                except (OSError, ValueError):
                    return reply("We couldn't save this request safely. Please try again later.", menu_button())
            session.update(candidate)
            return self.review(session)
        if action and action.startswith("arrival:"):
            parts = action.split(":")
            if (len(parts) not in (3, 4) or session.get("step") != "review_demo"
                    or not session.get("arrival_editable") or parts[1] != session.get("draft_id")):
                return reply("These arrival details are closed. Review or resume the saved request.", menu_button())
            if parts[2:] == ["review"]:
                return self.review(session)
            if parts[2:] == ["open"]:
                return self.arrival_options(session)
            if len(parts) != 4 or parts[3] not in ("0", "1", "2", "3", "4", "5"):
                return self.arrival_options(session)
            field, value = parts[2], int(parts[3])
            if field == "children" and value < session["guests"]:
                candidate = {**session, field: value}
            elif field in ("with_pet", "by_car") and value in (0, 1):
                candidate = {**session, field: bool(value)}
            else:
                return self.arrival_options(session)
            if self.draft_store:
                try:
                    self.draft_store.save(user_id, candidate)
                except (OSError, ValueError):
                    return reply("Couldn't save those details. Please resume and try again.", menu_button())
            session.update(candidate)
            return self.arrival_options(session)
        if action and action.startswith("send:"):
            if (not self.crm_client or session.get("step") not in ("review_demo", "submitted_demo")
                    or action != f"send:{session.get('draft_id')}"):
                return reply("This request has expired. Start a new sample stay.", [[("📅 Plan a stay", "plan")]] + menu_button())
            if session["step"] == "submitted_demo":
                return reply(f"Demo request received · {session['reference']}\n\nNo real booking or payment was made.", menu_button())
            if session.get("arrival_editable"):
                if self.draft_store:
                    try:
                        self.draft_store.save(user_id, {**session, "arrival_editable": False})
                    except (OSError, ValueError):
                        return reply("Couldn't prepare the request safely. Please resume and try again.", menu_button())
                session["arrival_editable"] = False
            payload = {"category_id": session["category_id"], "checkin": session["checkin"],
                       "checkout": session["checkout"], "guests": session["guests"]}
            for field in ("nightly_cents", "children", "with_pet", "by_car"):
                if field in session:
                    payload[field] = session[field]
            try:
                reference = self.crm_client.submit(payload, session["submission_key"])
            except CRMTransferError:
                return reply("We couldn't confirm whether the demo request arrived. Retry below while this session is open; "
                             "the same request identifier will be used. Use /resume after a restart. No real booking was made.",
                             [[("Retry demo request", f"send:{session['draft_id']}")]] + menu_button())
            session.update(step="submitted_demo", reference=reference)
            if self.draft_store:
                try:
                    self.draft_store.save(user_id, session)
                except (OSError, ValueError):
                    logging.warning("Could not update saved demo request; retry will reuse its identifier.")
            return reply(f"Demo request received · {reference}\n\nNo real booking or payment was made.", menu_button())
        if text and session.get("step") in ("checkin", "checkout"):
            try:
                cleaned = text.strip()
                if len(cleaned) != 10 or cleaned[4] != "-" or cleaned[7] != "-" or not (cleaned[:4] + cleaned[5:7] + cleaned[8:]).isdigit():
                    raise ValueError
                chosen = date.fromisoformat(cleaned)
            except ValueError:
                return reply("Please enter a valid date as YYYY-MM-DD, for example 2027-06-10.", menu_button())
            return select_date(session, chosen, today)
        return reply("Choose an option below or send /start to begin.", MENU)

class Telegram:
    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}/"

    def call(self, method, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base + method, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=40) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            # Do not print exception text or URLs, which may contain the token.
            raise RuntimeError(f"Telegram returned HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # The request URL contains the bot token; never include the exception text in logs.
            raise RuntimeError(f"Telegram request failed ({type(exc).__name__})") from None
        if not result.get("ok"):
            raise RuntimeError(f"Telegram returned an error (code {result.get('error_code', 'unknown')})")
        return result["result"]

def run(token, mini_app_url=None, crm_client=None):
    store = DraftStore(Path(__file__).resolve().parent / "data" / "drafts.sqlite3") if crm_client else None
    api, conversation, offset = Telegram(token), Conversation(mini_app_url, crm_client, store), None
    logging.info("Bot started. Stop with Ctrl+C.")
    connected = False
    while True:
        try:
            updates = api.call("getUpdates", {"offset": offset, "timeout": 25, "allowed_updates": ["message", "callback_query"]})
            if not connected:
                logging.info("Telegram long polling connected.")
                connected = True
            for update in updates:
                offset = update["update_id"] + 1
                callback = update.get("callback_query")
                message = update.get("message") or (callback or {}).get("message") or {}
                if message.get("chat", {}).get("type") != "private":
                    continue
                if callback:
                    api.call("answerCallbackQuery", {"callback_query_id": callback["id"]})
                user_id = (callback or message).get("from", {}).get("id")
                if user_id is None:
                    continue
                result = conversation.handle(user_id, text=message.get("text") if not callback else None, action=callback.get("data") if callback else None)
                if result is None:
                    continue
                if callback and callback.get("data", "").startswith(("cal:", "month:")):
                    api.call("editMessageText", {"chat_id": message["chat"]["id"], "message_id": message["message_id"], **result})
                else:
                    api.call("sendMessage", {"chat_id": message["chat"]["id"], **result})
        except RuntimeError as exc:
            if str(exc) in ("Telegram returned HTTP 401", "Telegram returned HTTP 409"):
                logging.error("%s. Check the token or whether another bot instance/webhook is active.", exc)
                return 1
            logging.warning("%s. Retrying in 5 seconds.", exc)
            time.sleep(5)

def demo():
    c = Conversation()
    sample = [("/start", None), (None, "resort"), (None, "plan"), ("2027-06-10", None), ("2027-06-14", None), (None, "guests:4"), (None, "budget:160")]
    for text, action in sample:
        result = c.handle(1, text=text, action=action, today=date(2027, 1, 1))
        print(f"\n> {text or action}\n{result['text']}")

def demo_crm():
    class PreviewCRM:
        def quotes(self, checkin, checkout, guests):
            nights = (date.fromisoformat(checkout) - date.fromisoformat(checkin)).days
            return [{**a, "nightly_cents": a["price"] * 100, "total_cents": a["price"] * nights * 100}
                    for a in APARTMENTS if a["guests"] >= guests]

        def submit(self, payload, key):
            return "demo-preview"
    conversation = Conversation(crm_client=PreviewCRM())
    print("OFFLINE PREVIEW: the CRM response is simulated; no network request is made.")
    steps = [(None, "plan"), ("2027-06-10", None), ("2027-06-14", None), (None, "guests:4"), (None, "budget:160")]
    for text, action in steps:
        result = conversation.handle(1, text=text, action=action, today=date(2027, 1, 1))
        print(f"\n> {text or action}\n{result['text']}")
    pick = result["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    result = conversation.handle(1, action=pick, today=date(2027, 1, 1))
    print(f"\n> Review\n{result['text']}")
    send = result["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    result = conversation.handle(1, action=send, today=date(2027, 1, 1))
    print(f"\n> Send (simulated)\n{result['text']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kinshore Bay portfolio Telegram bot")
    previews = parser.add_mutually_exclusive_group()
    previews.add_argument("--demo", action="store_true", help="show a sample conversation without Telegram or a token")
    previews.add_argument("--demo-mini-app", action="store_true", help="show the Mini App button with a placeholder URL, without Telegram or a token")
    previews.add_argument("--demo-crm", action="store_true", help="show a simulated demo request without network access")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if args.demo:
        demo()
    elif args.demo_mini_app:
        preview = home("https://example.com/site/miniapp.html")
        print(preview["text"])
        print("\nButtons: " + " | ".join(button["text"] for row in preview["reply_markup"]["inline_keyboard"] for button in row))
        print("\nExample URL only. Set MINI_APP_URL to the real HTTPS address when available.")
    elif args.demo_crm:
        demo_crm()
    else:
        try:
            token = load_bot_token()
            mini_app_url = load_mini_app_url()
            crm_client = load_crm_client()
        except ValueError as exc:
            parser.error(str(exc))
        if not token:
            parser.error("BOT_TOKEN is missing. Run bot/start.ps1 once to save it locally.")
        try:
            sys.exit(run(token, mini_app_url, crm_client))
        except KeyboardInterrupt:
            print("\nBot stopped.")
