"""Local prototype of authenticated machine-to-machine demo request intake."""
from datetime import date
import hashlib
import hmac
import json
import os
import re
from uuid import NAMESPACE_URL, UUID, uuid5

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.exceptions import RequestDataTooBig, ValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import DemoSubmission
from .services import _create_request, available_units

MAX_BODY_BYTES = 4096
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,256}\Z")
CODE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,15}\Z")
COMMON_FIELDS = {"checkin", "checkout", "guests"}
ARRIVAL_FIELDS = ("children", "with_pet", "by_car")

def response(data, status):
    result = JsonResponse(data, status=status)
    result["Cache-Control"] = "no-store"
    result["X-Content-Type-Options"] = "nosniff"
    return result

def service_actor(request):
    """Fail closed unless the configured secret and least-privilege service user exist."""
    expected = os.environ.get("KINSHORE_CRM_TOKEN", "")
    username = os.environ.get("KINSHORE_CRM_USER", "")
    if not TOKEN_PATTERN.fullmatch(expected) or not username:
        return None, 503
    header = request.headers.get("Authorization", "")
    prefix, separator, supplied = header.partition(" ")
    if not separator or prefix != "Bearer" or not TOKEN_PATTERN.fullmatch(supplied) or not hmac.compare_digest(expected, supplied):
        return None, 401
    actor = get_user_model().objects.filter(username=username, is_active=True).first()
    # The machine identity must not be capable of interactive or privileged use.
    if (actor is None or actor.is_superuser or actor.is_staff or actor.has_usable_password()
            or actor.get_all_permissions() != {"reception.add_stayrequest"}):
        return None, 503
    return actor, None

def parse_payload(request):
    if request.content_type != "application/json":
        raise ValueError
    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
        if length < 0 or length > MAX_BODY_BYTES:
            raise ValueError
        body = request.body
        if len(body) > MAX_BODY_BYTES:
            raise ValueError
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError
        expected = data.get("nightly_cents")
        if "nightly_cents" in data and (type(expected) is not int or expected < 0):
            raise ValueError
        if set(data) - {"nightly_cents", *ARRIVAL_FIELDS} not in (COMMON_FIELDS | {"apartment_code"}, COMMON_FIELDS | {"category_id"}):
            raise ValueError
        code, guests = data.get("apartment_code", data.get("category_id")), data["guests"]
        if not isinstance(code, str) or not CODE_PATTERN.fullmatch(code) or type(guests) is not int or not 1 <= guests <= 6:
            raise ValueError
        if "children" in data and (type(data["children"]) is not int or not 0 <= data["children"] < guests):
            raise ValueError
        if any(field in data and type(data[field]) is not bool for field in ("with_pet", "by_car")):
            raise ValueError
        for field in ("checkin", "checkout"):
            value = data[field]
            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                raise ValueError
        return data
    except (ValueError, TypeError, UnicodeDecodeError, RequestDataTooBig):
        raise ValueError("Invalid request.") from None

def replay(record, fingerprint, owner, arrival):
    if record.guest_owner != owner or record.payload_hash != fingerprint or record.stay_id is None:
        return response({"error": "Idempotency key already used for another request."}, 409)
    if owner and any(getattr(record.stay, field) != value for field, value in arrival.items()):
        return response({"error": "This trip already has a request. Check My stay and ask Reception about changes."}, 409)
    return response({"demo": True, "reference": record.stay.reference, "status": record.stay.status}, 200)

@csrf_exempt  # Machine-only bearer auth; no browser cookies or session authentication.
@require_POST
def create_demo_submission(request):
    if getattr(settings, "PUBLIC_DEMO", False):
        return response({"error": "Service unavailable."}, 503)
    _, error = service_actor(request)
    if error:
        return response({"error": "Service unavailable." if error == 503 else "Unauthorized."}, error)
    try:
        raw_key = request.headers.get("Idempotency-Key", "")
        key = UUID(raw_key)
        if str(key) != raw_key.lower():
            raise ValueError
        data = parse_payload(request)
    except (ValueError, AttributeError):
        return response({"error": "Invalid request or idempotency key."}, 400)

    return submit(data, key)


def submit(data, key, owner="", *, workspace=""):
    arrival = {field: data[field] for field in ARRIVAL_FIELDS if field in data}
    identity = {field: value for field, value in data.items() if not owner or field not in ("nightly_cents", *ARRIVAL_FIELDS)}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    if owner:
        # Recalculation after a lost response must still find the original trip.
        key = uuid5(NAMESPACE_URL, owner + fingerprint)
    try:
        with transaction.atomic():
            existing = DemoSubmission.objects.select_related("stay").filter(key=key).first()
            if existing:
                return replay(existing, fingerprint, owner, arrival)
            start = date.fromisoformat(data["checkin"])
            end = date.fromisoformat(data["checkout"])
            units = available_units(start, end, data["guests"], workspace=workspace)
            if "category_id" in data:
                units = units.filter(category__code=data["category_id"])
            else:
                units = units.filter(code=data["apartment_code"])
            unit = units.select_for_update().select_related("category").order_by("code").first()
            if unit is None:
                return response({"error": "No matching apartment for these dates."}, 400)
            # A confirmation may have committed while this transaction waited for the lock.
            if not units.filter(pk=unit.pk).exists():
                return response({"error": "Availability changed. Recalculate your stay."}, 409)
            if data.get("nightly_cents", unit.category.nightly_cents) != unit.category.nightly_cents:
                return response({"error": "The rate changed. Recalculate your stay."}, 409)
            entry = DemoSubmission.objects.create(key=key, payload_hash=fingerprint, guest_owner=owner)
            stay = _create_request(unit.pk, start, end, data["guests"], workspace=workspace, **arrival)
            entry.stay = stay
            entry.save(update_fields=["stay"])
            return response({"demo": True, "reference": stay.reference, "status": stay.status}, 201)
    except ValidationError:
        return response({"error": "Invalid demo request."}, 400)
    except IntegrityError:
        # A concurrent insert with the same key may have committed; no extra stay survives rollback.
        existing = DemoSubmission.objects.select_related("stay").filter(key=key).first()
        if existing:
            return replay(existing, fingerprint, owner, arrival)
        raise
