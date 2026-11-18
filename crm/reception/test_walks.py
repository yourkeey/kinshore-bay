from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from .access import OWNER_GROUP, RECEPTION_GROUP, setup_demo_roles
from .models import Apartment, StayRequest, WalkBooking, WalkSession
from .services import _change_status, _create_request
from .walks import sessions_with_totals, walks_for_stays

STAYS_URL = "/api/guest/stays/"
PAIR = {"adults": 1, "teens": 0, "children": 1}
SOLO = {"adults": 1, "teens": 0, "children": 0}


def future_walk():
    return WalkSession.objects.filter(day__gte=timezone.localdate() + timedelta(days=14)).earliest("day")


def guest_stay(walk, unit=None):
    guest = Client(enforce_csrf_checks=True)
    csrf = guest.get(STAYS_URL).json()["csrf"]
    checkin = walk.day - timedelta(days=1)
    checkout = walk.day + timedelta(days=1)
    result = guest.post(STAYS_URL, {
        "category_id": "one", "checkin": checkin.isoformat(), "checkout": checkout.isoformat(),
        "nightly_cents": 13500, "guests": 4,
    }, content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
    stay = StayRequest.objects.get(reference=result.json()["reference"])
    if unit:
        _change_status(stay.pk, "confirmed", apartment_code=unit)
    return guest, csrf, stay


def endpoint(stay, walk):
    return f"{STAYS_URL}{stay.reference}/walks/{walk.pk}/"


def book(guest, csrf, stay, walk, party=PAIR):
    return guest.post(endpoint(stay, walk), party, content_type="application/json", HTTP_X_CSRFTOKEN=csrf)


class WalkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        setup_demo_roles()
        cls.walk = future_walk()
        cls.staff = get_user_model().objects.create_user("walk-staff")
        cls.staff.groups.add(Group.objects.get(name=RECEPTION_GROUP))
        cls.owner = get_user_model().objects.create_user("walk-owner")
        cls.owner.groups.add(Group.objects.get(name=OWNER_GROUP))

    def reserved(self):
        return sessions_with_totals().get(pk=self.walk.pk).reserved

    def test_booking_requires_confirmation_csrf_and_ownership(self):
        guest, csrf, stay = guest_stay(self.walk)
        self.assertEqual(guest.get(STAYS_URL).json()["stays"][0]["walks"], [])
        self.assertEqual(book(guest, csrf, stay, self.walk).status_code, 409)
        _change_status(stay.pk, "confirmed")
        self.assertEqual(guest.post(endpoint(stay, self.walk), PAIR, content_type="application/json").status_code, 403)
        other = Client(enforce_csrf_checks=True)
        other_csrf = other.get(STAYS_URL).json()["csrf"]
        self.assertEqual(book(other, other_csrf, stay, self.walk).status_code, 404)
        self.assertEqual(book(guest, csrf, stay, self.walk, {"adults": 0, "teens": 1, "children": 1}).status_code, 409)
        self.assertEqual(book(guest, csrf, stay, self.walk, {"adults": 0, "teens": 1, "children": 0}).status_code, 200)
        self.assertEqual(self.reserved(), 1)

    def test_last_seats_retry_guest_cancellation_and_stay_cancellation(self):
        guest, csrf, stay = guest_stay(self.walk, "A-102")
        second, second_csrf, second_stay = guest_stay(self.walk, "B-102")
        unit = Apartment.objects.get(code="A-103")
        filler = _create_request(unit.pk, stay.checkin, stay.checkout, 6)
        _change_status(filler.pk, "confirmed")
        WalkBooking.objects.create(session=self.walk, stay=filler, adults=6, children=0)
        self.assertEqual(book(guest, csrf, stay, self.walk).status_code, 200)
        self.assertEqual(book(guest, csrf, stay, self.walk).status_code, 200)
        self.assertEqual(self.reserved(), 8)
        self.assertEqual(book(second, second_csrf, second_stay, self.walk).status_code, 409)
        self.assertEqual(guest.delete(endpoint(stay, self.walk), HTTP_X_CSRFTOKEN=csrf).status_code, 200)
        self.assertEqual(guest.delete(endpoint(stay, self.walk), HTTP_X_CSRFTOKEN=csrf).status_code, 200)
        self.assertEqual(self.reserved(), 6)
        self.assertEqual(book(guest, csrf, stay, self.walk, SOLO).status_code, 200)
        result = book(second, second_csrf, second_stay, self.walk)
        self.assertEqual(result.status_code, 409)
        self.assertIn("Only 1 seat left", result.json()["error"])
        self.assertEqual(book(second, second_csrf, second_stay, self.walk, SOLO).status_code, 200)
        _change_status(stay.pk, "cancelled")
        self.assertEqual(self.reserved(), 7)
        self.assertEqual(guest.get(STAYS_URL).json()["stays"][0]["walks"], [])

    def test_desk_roster_and_club_cancellation(self):
        guest, csrf, stay = guest_stay(self.walk, "A-102")
        book(guest, csrf, stay, self.walk)
        url = f"{reverse('desk-walks')}?day={self.walk.day.isoformat()}"
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(url), stay.reference)
        payload = {"action": "cancel", "day": self.walk.day.isoformat()}
        self.assertEqual(self.client.post(url, payload).status_code, 403)
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(url), "2 of 8 places reserved")
        self.assertRedirects(self.client.post(url, payload), url)
        state = guest.get(STAYS_URL).json()["stays"][0]
        self.assertEqual(state["status"], "confirmed")
        self.assertTrue(state["walks"][0]["cancelled"])
        self.assertFalse(state["walks"][0]["open"])

    def test_walk_is_visible_on_checkout_morning_but_not_on_arrival_morning(self):
        unit = Apartment.objects.get(code="A-103")
        stay = _create_request(unit.pk, self.walk.day, self.walk.day + timedelta(days=1), 2)
        _change_status(stay.pk, "confirmed")
        stay.refresh_from_db()
        self.assertEqual(walks_for_stays([stay])[stay.pk], [])
        stay.checkin, stay.checkout = self.walk.day - timedelta(days=1), self.walk.day
        self.assertEqual(walks_for_stays([stay])[stay.pk][0]["id"], self.walk.pk)


class WalkRaceTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_two_guests_compete_for_last_seat(self):
        call_command("seed_demo", verbosity=0)
        walk = future_walk()
        walk.capacity = 1
        walk.save(update_fields=["capacity"])
        guests = [guest_stay(walk, unit) for unit in ("A-102", "B-102")]
        ready = Barrier(2)

        def synchronize_walk_lock(execute, sql, params, many, context):
            if 'FROM "reception_walksession"' in sql and "FOR UPDATE" in sql:
                ready.wait(timeout=10)
            return execute(sql, params, many, context)

        def reserve(guest, csrf, stay):
            try:
                with connection.execute_wrapper(synchronize_walk_lock):
                    return book(guest, csrf, stay, walk, SOLO).status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [executor.submit(reserve, *guest) for guest in guests]
            self.assertCountEqual([result.result(timeout=20) for result in results], [200, 409])
        self.assertEqual(sessions_with_totals().get(pk=walk.pk).reserved, 1)
