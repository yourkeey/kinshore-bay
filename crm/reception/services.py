"""Application rules for fictional requests; every state transition must go through here."""
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import transaction
from .access import require_permission
from .grills import release_future_grills
from .models import Apartment, StatusChange, StayRequest
from .walks import release_future_walks

TRANSITIONS = {
    "requested": {"confirmed", "cancelled"},
    "confirmed": {"checked_in", "cancelled"},
    "checked_in": {"checked_out"},
    "checked_out": set(),
    "cancelled": set(),
}
BLOCKING = ("confirmed", "checked_in", "checked_out")

def list_requests(*, actor, workspace=""):
    require_permission(actor, "view_stayrequest")
    return StayRequest.objects.filter(workspace=workspace).select_related("apartment").order_by("checkin", "reference")

def list_apartments(*, actor):
    require_permission(actor, "view_apartment")
    return Apartment.objects.select_related("building", "category").order_by("code")

def require_owner_analytics(*, actor):
    """Reserve the permission check for a future analytics service; no metrics exist yet."""
    require_permission(actor, "view_owner_analytics")

def create_request(apartment_id, checkin, checkout, guests, *, actor, reference=None):
    require_permission(actor, "add_stayrequest")
    return _create_request(apartment_id, checkin, checkout, guests, reference=reference)

@transaction.atomic
def _create_request(apartment_id, checkin, checkout, guests, *, reference=None, children=None, with_pet=None, by_car=None, workspace=""):
    apartment = Apartment.objects.select_for_update().get(pk=apartment_id)
    request = StayRequest(reference=reference or uuid4().hex[:12], apartment=apartment, checkin=checkin,
                          checkout=checkout, guests=guests, nightly_cents=apartment.category.nightly_cents,
                          children=children, with_pet=with_pet, by_car=by_car, workspace=workspace)
    request.full_clean()
    request.save()
    return request

def change_status(request_id, new_status, *, actor, apartment_code=None, workspace=""):
    require_permission(actor, "change_stayrequest")
    return _change_status(request_id, new_status, actor=actor, apartment_code=apartment_code, workspace=workspace)

@transaction.atomic
def _change_status(request_id, new_status, *, actor=None, apartment_code=None, workspace=""):
    current = StayRequest.objects.select_for_update().get(pk=request_id, workspace=workspace)
    previous_unit = current.apartment.code
    if new_status not in TRANSITIONS[current.status]:
        raise ValidationError("This status change is not allowed.")
    if new_status == StayRequest.Status.CONFIRMED:
        # Competing stays must lock the same destination before checking its dates.
        units = Apartment.objects.select_for_update().filter(category_id=current.apartment.category_id)
        target = units.filter(code=apartment_code or previous_unit).first()
        if target is None:
            raise ValidationError("Choose an apartment in the requested category.")
        current.apartment = target
        overlap = StayRequest.objects.filter(workspace=workspace, apartment_id=current.apartment_id, status__in=BLOCKING,
                    checkin__lt=current.checkout, checkout__gt=current.checkin).exclude(pk=current.pk).exists()
        if overlap:
            raise ValidationError("That apartment already has a confirmed demo stay during those dates.")
    previous = current.status
    current.status = new_status
    current.full_clean()
    current.save(update_fields=["status", "apartment"])
    if new_status in (StayRequest.Status.CANCELLED, StayRequest.Status.CHECKED_OUT):
        release_future_walks(current)
        release_future_grills(current)
    StatusChange.objects.create(stay=current, actor=actor, previous=previous, current=new_status,
                                previous_unit=previous_unit, current_unit=current.apartment.code)
    return current

def available_units(start, end, guests, *, workspace=""):
    blocked = StayRequest.objects.filter(workspace=workspace, status__in=BLOCKING, checkin__lt=end,
                                         checkout__gt=start).values("apartment_id")
    return Apartment.objects.filter(category__capacity__gte=guests).exclude(pk__in=blocked)


def quote_stays(start, end, guests, *, workspace=""):
    nights = (end - start).days
    if not 1 <= nights <= 90 or not 1 <= guests <= 6:
        raise ValidationError("Choose valid dates and guest count.")
    categories = available_units(start, end, guests, workspace=workspace).order_by("category__nightly_cents").values_list(
        "category__code", "category__name", "category__capacity", "category__nightly_cents").distinct()
    return [{"id": code, "name": name, "guests": capacity, "nightly_cents": cents,
             "total_cents": cents * nights} for code, name, capacity, cents in categories]
