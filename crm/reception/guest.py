"""Guest-facing, same-origin demo routes."""
import hashlib
import json
from datetime import date
from pathlib import Path
from secrets import token_hex

from django.core.exceptions import RequestDataTooBig, ValidationError
from django.http import FileResponse, Http404
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from .api import MAX_BODY_BYTES, parse_payload, response, submit
from .grills import grills_for_stays
from .models import ApartmentType, DemoSubmission, WalkSession
from .services import quote_stays
from .walks import ELIGIBLE, change_booking, walks_for_stays

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"


@require_GET
def site_file(request, name="index.html"):
    target = (SITE / name).resolve()
    if not target.is_relative_to(SITE) or target.suffix not in {".html", ".css", ".js", ".svg", ".webp"} or not target.is_file():
        raise Http404
    return FileResponse(target.open("rb"))


@require_GET
def catalog(request):
    data = json.loads((ROOT / "content/en.json").read_text(encoding="utf-8"))
    categories = {row.code: row for row in ApartmentType.objects.all()}
    rooms = []
    for room in data["apartments"]:
        row = categories.get(room["id"])
        if row:
            rooms.append({**room, "name": row.name, "price": row.nightly_cents / 100, "guests": row.capacity})
    data["apartments"] = rooms
    return response(data, 200)


def validate_window(start):
    if not 0 <= (start - timezone.localdate()).days <= 730:
        raise ValueError


@require_GET
def quotes(request):
    try:
        start = date.fromisoformat(request.GET["checkin"])
        end = date.fromisoformat(request.GET["checkout"])
        validate_window(start)
        rows = quote_stays(start, end, int(request.GET["guests"]), workspace=getattr(request, "workspace", ""))
    except (KeyError, ValueError, OverflowError, ValidationError):
        return response({"error": "Choose a valid stay of up to 90 nights."}, 400)
    return response({"rooms": rows}, 200)


def guest_owner(request, *, create=False):
    owner = getattr(request, "workspace", "") or request.session.get("kinshore_guest")
    if not isinstance(owner, str):
        if owner is True and request.session.session_key:
            owner = hashlib.sha256(request.session.session_key.encode()).hexdigest()
        elif create:
            owner = token_hex(32)
        else:
            return None
        request.session["kinshore_guest"] = owner
    return owner


@require_http_methods(["GET", "POST"])
def my_stays(request):
    owner = guest_owner(request, create=request.method == "GET")
    if not owner:
        return response({"error": "Open My stay first and enable cookies."}, 400)
    if request.method == "GET":
        entries = DemoSubmission.objects.filter(guest_owner=owner, stay__isnull=False).select_related(
            "stay__apartment__category", "stay__apartment__building").order_by("-created_at")
        stays = [entry.stay for entry in entries]
        walks = walks_for_stays(stays, workspace=getattr(request, "workspace", ""))
        grills = grills_for_stays(stays)
        rows = []
        for stay in stays:
            rows.append({"reference": stay.reference, "status": stay.status, "room": stay.apartment.category.name,
                         "checkin": stay.checkin, "checkout": stay.checkout, "guests": stay.guests,
                         "children": stay.children, "with_pet": stay.with_pet, "by_car": stay.by_car,
                         "total_cents": stay.nightly_cents * (stay.checkout - stay.checkin).days,
                         "building": stay.apartment.building.code if stay.status in ELIGIBLE else None,
                         "walks": walks[stay.pk], "grills": grills[stay.pk]})
        return response({"stays": rows, "csrf": get_token(request)}, 200)
    try:
        data = parse_payload(request)
        if "category_id" not in data or "nightly_cents" not in data:
            raise ValueError
        validate_window(date.fromisoformat(data["checkin"]))
    except ValueError:
        return response({"error": "Check your dates and recalculate."}, 400)
    return submit(data, None, owner=owner, workspace=getattr(request, "workspace", ""))


@require_http_methods(["POST", "DELETE"])
def walk_booking(request, reference, walk_id):
    owner = guest_owner(request)
    if not owner:
        return response({"error": "Stay not found in this browser session."}, 404)
    stay_id = DemoSubmission.objects.filter(guest_owner=owner, stay__reference=reference).values_list("stay_id", flat=True).first()
    if stay_id is None:
        return response({"error": "Stay not found in this browser session."}, 404)
    party = None
    if request.method == "POST":
        try:
            if request.content_type != "application/json" or len(request.body) > MAX_BODY_BYTES:
                raise ValueError
            data = json.loads(request.body)
            if not isinstance(data, dict) or set(data) != {"adults", "teens", "children"}:
                raise ValueError
            party = (data["adults"], data["teens"], data["children"])
            if any(type(count) is not int for count in party):
                raise ValueError
        except (ValueError, RequestDataTooBig):
            return response({"error": "Choose the number of adults and children."}, 400)
    try:
        change_booking(stay_id, walk_id, party)
    except WalkSession.DoesNotExist:
        return response({"error": "Walk not found."}, 404)
    except ValidationError as exc:
        return response({"error": exc.messages[0]}, 409)
    return response({"ok": True}, 200)
