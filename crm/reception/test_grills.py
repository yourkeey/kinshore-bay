from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Apartment, GrillBooking
from .services import _change_status, _create_request


class GrillScheduleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.staff = get_user_model().objects.create_superuser(username="grill-test")
        cls.day = timezone.localdate() + timedelta(days=20)
        units = list(Apartment.objects.order_by("code")[:2])
        cls.stays = [_create_request(unit.pk, cls.day, cls.day + timedelta(days=2), 2) for unit in units]
        for stay in cls.stays:
            _change_status(stay.pk, "confirmed")

    def setUp(self):
        self.client.force_login(self.staff)
        self.url = reverse("desk-grills")

    def book(self, stay, **options):
        fields = {"day": self.day.isoformat(), "action": "reserve", "slot": 17, "table": 1, "reference": stay.reference}
        return self.client.post(self.url, {**fields, **options})

    def test_conflicts_and_stay_cancellation_release_the_table(self):
        first, second = self.stays
        self.assertEqual(self.book(first).status_code, 302)
        self.assertEqual(self.book(first).status_code, 302)
        self.assertEqual(GrillBooking.objects.count(), 1)
        self.assertContains(self.book(first, table=2), "already has a grill table", status_code=409)
        self.assertContains(self.book(second), "already reserved", status_code=409)
        _change_status(first.pk, "cancelled")
        self.assertEqual(self.book(second).status_code, 302)
        self.assertEqual(GrillBooking.objects.get(cancelled=False).stay_id, second.pk)

    def test_checkout_day_and_cancelled_stays_cannot_be_booked(self):
        first, second = self.stays
        self.assertEqual(self.book(first, day=first.checkout.isoformat()).status_code, 409)
        self.assertEqual(self.book(first, table=3).status_code, 409)
        _change_status(second.pk, "cancelled")
        self.assertEqual(self.book(second).status_code, 409)
        self.assertFalse(GrillBooking.objects.exists())
