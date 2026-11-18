from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .access import require_permission
from .grills import TABLES, cancel_grill, reserve_grill, slot_is_future
from .models import GrillBooking, StayRequest
from .services import BLOCKING, TRANSITIONS, available_units, change_status, list_apartments, list_requests
from .walks import MEETING, MEETING_POINT, START, TITLE, cancel_walk, ensure_walk_sessions, session_open, sessions_with_totals


@never_cache
@login_required
@require_GET
def today(request):
    day = timezone.localdate()
    stays = list_requests(actor=request.user, workspace=getattr(request, "workspace", ""))
    query = request.GET.get("q", "").strip()
    if query:
        sections = [("Search results", stays.filter(reference__iexact=query))]
    else:
        sections = [
            ("Arrivals", stays.filter(checkin=day, status__in=("confirmed", "checked_in"))),
            ("Departures", stays.filter(checkout=day, status__in=BLOCKING)),
            ("New requests", stays.filter(status="requested").order_by("created_at")),
        ]
    return render(request, "desk/today.html", {"day": day, "sections": sections, "q": query})


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def detail(request, reference):
    workspace = getattr(request, "workspace", "")
    stays = list_requests(actor=request.user, workspace=workspace).select_related("apartment__category")
    stay = get_object_or_404(stays, reference=reference)
    error = ""
    if request.method == "POST":
        try:
            change_status(stay.pk, request.POST.get("status"), actor=request.user,
                          apartment_code=request.POST.get("unit"), workspace=workspace)
            return redirect("desk-detail", reference=reference)
        except ValidationError as exc:
            error = " ".join(exc.messages)
            stay.refresh_from_db()
    free = []
    if stay.status == StayRequest.Status.REQUESTED:
        free = list(available_units(stay.checkin, stay.checkout, stay.guests, workspace=workspace)
                    .filter(category_id=stay.apartment.category_id).order_by("code"))
    actions = TRANSITIONS[stay.status]
    total = Decimal(stay.nightly_cents * (stay.checkout - stay.checkin).days) / 100
    return render(request, "desk/detail.html", {
        "stay": stay,
        "free": free,
        "assigned_available": stay.apartment in free,
        "total": total,
        "actions": actions,
        "error": error,
        "history": stay.changes.select_related("actor").order_by("-created_at", "-pk"),
    }, status=409 if error else 200)


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def grills(request):
    require_permission(request.user, "view_stayrequest")
    workspace = getattr(request, "workspace", "")
    now = timezone.localtime()
    fields = request.POST if request.method == "POST" else request.GET
    try:
        day = date.fromisoformat(fields.get("day", now.date().isoformat()))
    except ValueError:
        return render(request, "desk/grills.html", {"day": now.date(), "error": "Choose a valid date."}, status=400)

    error = ""
    if request.method == "POST":
        require_permission(request.user, "change_stayrequest")
        try:
            if fields.get("action") == "reserve":
                reserve_grill(fields.get("reference", "").strip(), day, int(fields.get("slot", "")),
                              int(fields.get("table", "")), actor=request.user, workspace=workspace)
            elif fields.get("action") == "cancel":
                booking_id = int(fields.get("booking", ""))
                if not 1 <= booking_id <= 2**63 - 1:
                    raise ValueError
                cancel_grill(booking_id, day, actor=request.user, workspace=workspace)
            else:
                raise ValueError
        except ValidationError as exc:
            error = exc.messages[0]
        except ValueError:
            error = "Choose a table and time from the schedule."
        if not error:
            return redirect(f"{reverse('desk-grills')}?day={day.isoformat()}")

    bookings = {(booking.slot, booking.table): booking for booking in
                GrillBooking.objects.filter(workspace=workspace, day=day, cancelled=False).select_related("stay__apartment")}
    rows = [
        {"slot": slot, "time": label, "table": table, "booking": bookings.get((slot, table)),
         "upcoming": slot_is_future(day, slot, now)}
        for slot, label in GrillBooking.Slot.choices for table in TABLES
    ]
    return render(request, "desk/grills.html", {"day": day, "rows": rows, "error": error}, status=409 if error else 200)


@never_cache
@login_required
@require_GET
def calendar(request):
    apartments = list_apartments(actor=request.user)
    stays = list_requests(actor=request.user, workspace=getattr(request, "workspace", ""))
    try:
        start = date.fromisoformat(request.GET.get("start", timezone.localdate().isoformat()))
        days = [start + timedelta(days=i) for i in range(7)]
    except (ValueError, OverflowError):
        return render(request, "desk/calendar.html", {"error": "Choose a valid week."}, status=400)
    occupied = stays.filter(status__in=BLOCKING, checkin__lte=days[-1], checkout__gt=start)
    cells = {(s.apartment_id, day): s for s in occupied for day in days if s.checkin <= day < s.checkout}
    rows = [(unit, [cells.get((unit.pk, day)) for day in days]) for unit in apartments]
    return render(request, "desk/calendar.html", {"start": start, "days": days, "rows": rows})


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def walks(request):
    require_permission(request.user, "view_stayrequest")
    workspace = getattr(request, "workspace", "")
    sessions = sessions_with_totals(workspace)
    now = timezone.localtime()
    raw_day = request.GET.get("day")
    if request.method == "POST":
        require_permission(request.user, "change_stayrequest")
        raw_day = request.POST.get("day", "")
    if raw_day is None:
        if workspace:
            ensure_walk_sessions(workspace, now.date(), now.date() + timedelta(days=7))
        session = sessions.filter(day__gte=now.date()).order_by("day").first()
        day = session.day if session else now.date()
    else:
        try:
            day = date.fromisoformat(raw_day)
        except ValueError:
            return render(request, "desk/walks.html", {"error": "Choose a valid date."}, status=400)
        if workspace and 0 <= (day - now.date()).days <= 820:
            ensure_walk_sessions(workspace, day, day)
        session = sessions.filter(day=day).first()

    error = ""
    if request.method == "POST":
        if session is None or request.POST.get("action") != "cancel":
            return render(request, "desk/walks.html", {"day": day, "error": "Choose a walk to cancel."}, status=400)
        try:
            cancel_walk(session.pk, workspace=workspace)
            return redirect(f"{reverse('desk-walks')}?day={day.isoformat()}")
        except ValidationError as exc:
            error = exc.messages[0]

    return render(request, "desk/walks.html", {
        "day": day,
        "error": error,
        "session": session,
        "bookings": session.bookings.filter(cancelled=False).select_related("stay__apartment").order_by("stay__reference") if session else [],
        "can_cancel": session and not session.cancelled and session_open(day, now),
        "title": TITLE,
        "meeting_at": MEETING,
        "meeting_point": MEETING_POINT,
        "starts_at": START,
    }, status=409 if error else 200)
