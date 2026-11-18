"""Local-demo inventory and stay requests."""
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q

class Building(models.Model):
    code = models.CharField(max_length=8, unique=True)

    def __str__(self):
        return self.code

class ApartmentType(models.Model):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    capacity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    nightly_cents = models.PositiveIntegerField()

    def __str__(self):
        return self.name

class Apartment(models.Model):
    code = models.CharField(max_length=16, unique=True)
    building = models.ForeignKey(Building, on_delete=models.PROTECT, related_name="apartments")
    category = models.ForeignKey(ApartmentType, on_delete=models.PROTECT, related_name="apartments")

    def __str__(self):
        return self.code

class StayRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        CONFIRMED = "confirmed", "Confirmed"
        CHECKED_IN = "checked_in", "Checked in"
        CHECKED_OUT = "checked_out", "Checked out"
        CANCELLED = "cancelled", "Cancelled"

    reference = models.CharField(max_length=32, unique=True)
    workspace = models.CharField(max_length=64, blank=True, default="", db_index=True)
    apartment = models.ForeignKey(Apartment, on_delete=models.PROTECT, related_name="requests")
    checkin = models.DateField()
    checkout = models.DateField()
    guests = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    children = models.PositiveSmallIntegerField(null=True, blank=True)
    with_pet = models.BooleanField(null=True, blank=True)
    by_car = models.BooleanField(null=True, blank=True)
    nightly_cents = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REQUESTED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        permissions = [("view_owner_analytics", "Can view owner analytics")]
        constraints = [
            models.CheckConstraint(condition=Q(checkout__gt=F("checkin")), name="stay_checkout_after_checkin"),
            models.CheckConstraint(condition=Q(guests__gte=1), name="stay_positive_guests"),
            models.CheckConstraint(condition=Q(children__isnull=True) | Q(children__lt=F("guests")), name="stay_children_have_adult"),
            models.CheckConstraint(condition=Q(status__in=["requested", "confirmed", "checked_in", "checked_out", "cancelled"]), name="stay_valid_status"),
        ]
        indexes = [models.Index(fields=["apartment", "checkin", "checkout"], name="stay_unit_dates_idx")]

    def clean(self):
        super().clean()
        if self.checkin and self.checkout:
            duration = self.checkout - self.checkin
            if not timedelta(days=1) <= duration <= timedelta(days=90):
                raise ValidationError("Check-out must follow check-in; stays are limited to 90 nights.")
        if self.apartment_id and self.guests and self.guests > self.apartment.category.capacity:
            raise ValidationError("Guest count exceeds the apartment's capacity.")

    def __str__(self):
        return self.reference

class DemoSubmission(models.Model):
    """Idempotency record for a guest or machine-to-machine demo submission."""
    key = models.UUIDField(unique=True)
    guest_owner = models.CharField(max_length=64, blank=True, default="", db_index=True)
    payload_hash = models.CharField(max_length=64)
    stay = models.OneToOneField(StayRequest, on_delete=models.PROTECT, null=True, related_name="demo_submission")
    created_at = models.DateTimeField(auto_now_add=True)


class StatusChange(models.Model):
    stay = models.ForeignKey(StayRequest, on_delete=models.CASCADE, related_name="changes")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    previous = models.CharField(max_length=16, choices=StayRequest.Status.choices)
    current = models.CharField(max_length=16, choices=StayRequest.Status.choices)
    previous_unit = models.CharField(max_length=16)
    current_unit = models.CharField(max_length=16)


class WalkSession(models.Model):
    day = models.DateField()
    workspace = models.CharField(max_length=64, blank=True, default="")
    capacity = models.PositiveSmallIntegerField(default=8)
    cancelled = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "day"], name="walk_one_session_per_workspace_day"),
            models.CheckConstraint(condition=Q(capacity__gte=1), name="walk_positive_capacity"),
        ]


class WalkBooking(models.Model):
    session = models.ForeignKey(WalkSession, on_delete=models.PROTECT, related_name="bookings")
    stay = models.ForeignKey(StayRequest, on_delete=models.PROTECT, related_name="walk_bookings")
    adults = models.PositiveSmallIntegerField()
    teens = models.PositiveSmallIntegerField(default=0)
    children = models.PositiveSmallIntegerField()
    cancelled = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["session", "stay"], name="walk_one_booking_per_stay"),
            models.CheckConstraint(condition=Q(adults__gte=1) | Q(teens__gte=1), name="walk_nonempty_party"),
            models.CheckConstraint(condition=Q(children=0) | Q(adults__gte=1), name="walk_children_accompanied"),
        ]


class GrillBooking(models.Model):
    class Slot(models.IntegerChoices):
        EARLY = 17, "17:00–19:00"
        LATE = 19, "19:00–21:00"

    stay = models.ForeignKey(StayRequest, on_delete=models.PROTECT, related_name="grill_bookings")
    workspace = models.CharField(max_length=64, blank=True, default="")
    day = models.DateField()
    slot = models.PositiveSmallIntegerField(choices=Slot.choices)
    table = models.PositiveSmallIntegerField()
    cancelled = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(slot__in=[17, 19]), name="grill_valid_slot"),
            models.CheckConstraint(condition=Q(table__in=[1, 2]), name="grill_valid_table"),
            models.UniqueConstraint(fields=["workspace", "day", "slot", "table"], condition=Q(cancelled=False), name="grill_one_party_per_workspace_table"),
            models.UniqueConstraint(fields=["stay", "day"], condition=Q(cancelled=False), name="grill_one_table_per_stay_night"),
        ]
