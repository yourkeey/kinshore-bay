"""Reception allocations for the two grill tables."""
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .access import require_permission
from .models import GrillBooking, StayRequest
from .walks import ELIGIBLE

TABLES = (1, 2)


def slot_is_future(day, slot, now):
    return (day, slot) > (now.date(), now.hour)


def reserve_grill(reference, day, slot, table, *, actor, workspace=""):
    require_permission(actor, "change_stayrequest")
    if slot not in GrillBooking.Slot.values or table not in TABLES:
        raise ValidationError("Choose an available grill slot and table.")
    try:
        with transaction.atomic():
            stay = StayRequest.objects.select_for_update().filter(workspace=workspace, reference__iexact=reference).first()
            if not stay or stay.status not in ELIGIBLE or not stay.checkin <= day < stay.checkout:
                raise ValidationError("Enter a confirmed stay that includes this evening.")
            if not slot_is_future(day, slot, timezone.localtime()):
                raise ValidationError("This grill slot has already started.")
            existing = stay.grill_bookings.filter(day=day, cancelled=False).first()
            if existing:
                if (existing.slot, existing.table) == (slot, table):
                    return
                raise ValidationError("This stay already has a grill table for that evening.")
            GrillBooking.objects.create(stay=stay, workspace=workspace, day=day, slot=slot, table=table)
    except IntegrityError as exc:
        if not GrillBooking.objects.filter(workspace=workspace, day=day, slot=slot, table=table, cancelled=False).exists():
            raise
        raise ValidationError("That table is already reserved. Choose another slot or table.") from exc


@transaction.atomic
def cancel_grill(booking_id, day, *, actor, workspace=""):
    require_permission(actor, "change_stayrequest")
    booking = GrillBooking.objects.select_for_update().filter(pk=booking_id, workspace=workspace, day=day, cancelled=False).first()
    if not booking:
        return
    if not slot_is_future(day, booking.slot, timezone.localtime()):
        raise ValidationError("This grill slot has already started.")
    booking.cancelled = True
    booking.save(update_fields=["cancelled"])


def release_future_grills(stay):
    now = timezone.localtime()
    stay.grill_bookings.filter(cancelled=False).filter(
        Q(day__gt=now.date()) | Q(day=now.date(), slot__gt=now.hour)
    ).update(cancelled=True)


def grills_for_stays(stays):
    records = {stay.pk: [] for stay in stays}
    for booking in GrillBooking.objects.filter(stay_id__in=records, cancelled=False).order_by("day", "slot"):
        records[booking.stay_id].append({"day": booking.day, "time": booking.get_slot_display(), "table": booking.table})
    return records
