"""Availability and reservations for the Saturday club walk."""
from datetime import time, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from .models import StayRequest, WalkBooking, WalkSession

START = time(10)
END = time(10, 45)
MEETING = time(9, 50)
MEETING_POINT = "Pine terrace"
TITLE = "Pine & Shore Walk"
ELIGIBLE = (StayRequest.Status.CONFIRMED, StayRequest.Status.CHECKED_IN)


def session_open(day, now):
    return (day, START) > (now.date(), now.time())


def on_stay(day, stay):
    # The morning walk ends before check-out and starts before check-in.
    return stay.checkin < day <= stay.checkout


def sessions_with_totals(workspace=""):
    return WalkSession.objects.filter(workspace=workspace).annotate(
        reserved=Sum(F("bookings__adults") + F("bookings__teens") + F("bookings__children"),
                     filter=Q(bookings__cancelled=False), default=0),
    )


def seed_walk_sessions(today):
    saturday = today + timedelta(days=(5 - today.weekday()) % 7)
    # Cover the latest possible arrival plus the longest supported stay.
    WalkSession.objects.bulk_create(
        [WalkSession(day=saturday + timedelta(weeks=week)) for week in range(118)],
        ignore_conflicts=True,
    )


def ensure_walk_sessions(workspace, start, end):
    saturday = start + timedelta(days=(5 - start.weekday()) % 7)
    days = (saturday + timedelta(weeks=i) for i in range(max(0, (end - saturday).days // 7 + 1)))
    WalkSession.objects.bulk_create([WalkSession(workspace=workspace, day=day) for day in days], ignore_conflicts=True)


def walks_for_stays(stays, *, workspace=""):
    if not stays:
        return {}
    now = timezone.localtime()
    active = [stay for stay in stays if stay.status in ELIGIBLE]
    bookings = {(booking.stay_id, booking.session_id): booking for booking in WalkBooking.objects.filter(
        stay_id__in=[stay.pk for stay in stays], cancelled=False,
    )}
    dates = Q(pk__in={session_id for _, session_id in bookings})
    if active:
        if workspace:
            for stay in active:
                ensure_walk_sessions(workspace, max(now.date(), stay.checkin), stay.checkout)
        dates |= Q(day__gte=max(now.date(), min(stay.checkin for stay in active)),
                   day__lte=max(stay.checkout for stay in active))
    sessions = list(sessions_with_totals(workspace).filter(dates).order_by("day"))
    rows = {}
    for stay in stays:
        options = []
        for session in sessions:
            booked = bookings.get((stay.pk, session.pk))
            open_for_stay = stay.status in ELIGIBLE and session_open(session.day, now) and on_stay(session.day, stay)
            if booked or open_for_stay:
                options.append({
                    "id": session.pk,
                    "day": session.day,
                    "title": TITLE,
                    "meeting_at": MEETING.strftime("%H:%M"),
                    "starts_at": START.strftime("%H:%M"),
                    "ends_at": END.strftime("%H:%M"),
                    "meeting_point": MEETING_POINT,
                    "capacity": session.capacity,
                    "remaining": max(session.capacity - session.reserved, 0),
                    "cancelled": session.cancelled,
                    "open": open_for_stay and not session.cancelled,
                    "booking": {"seats": booked.adults + booked.teens + booked.children} if booked else None,
                })
        rows[stay.pk] = options
    return rows


@transaction.atomic
def change_booking(stay_id, session_id, party=None):
    """Lock the stay and then the session. A pending request cannot hold seats."""
    stay = StayRequest.objects.select_for_update().get(pk=stay_id)
    session = WalkSession.objects.select_for_update().get(pk=session_id, workspace=stay.workspace)
    booking = WalkBooking.objects.filter(stay=stay, session=session).first()
    if party is None and (booking is None or booking.cancelled):
        return
    if (stay.status not in ELIGIBLE or not on_stay(session.day, stay)
            or not session_open(session.day, timezone.localtime()) or session.cancelled):
        raise ValidationError("This walk is closed to changes.")
    if party is None:
        booking.cancelled = True
        booking.save(update_fields=["cancelled"])
        return

    adults, teens, children = party
    seats = sum(party)
    if min(party) < 0 or not 1 <= seats <= stay.guests:
        raise ValidationError("Choose at least one participant and stay within your guest count.")
    if children and not adults:
        raise ValidationError("Participants under 16 must be accompanied by an adult.")
    if booking and not booking.cancelled:
        if (booking.adults, booking.teens, booking.children) == party:
            return
        raise ValidationError("Cancel the current booking to change the number of participants.")

    remaining = session.capacity - sessions_with_totals(stay.workspace).values_list("reserved", flat=True).get(pk=session.pk)
    if remaining < seats:
        available = max(remaining, 0)
        suffix = "" if available == 1 else "s"
        raise ValidationError(f"Only {available} seat{suffix} left. Choose fewer participants or another session.")
    WalkBooking.objects.update_or_create(
        stay=stay, session=session, defaults={"adults": adults, "teens": teens, "children": children, "cancelled": False},
    )


def release_future_walks(stay):
    now = timezone.localtime()
    day = now.date() if now.time() < START else now.date() + timedelta(days=1)
    stay.walk_bookings.filter(session__day__gte=day, cancelled=False).update(cancelled=True)


@transaction.atomic
def cancel_walk(session_id, *, workspace=""):
    session = WalkSession.objects.select_for_update().get(pk=session_id, workspace=workspace)
    if not session_open(session.day, timezone.localtime()):
        raise ValidationError("This walk has already started.")
    if not session.cancelled:
        session.cancelled = True
        session.save(update_fields=["cancelled"])
