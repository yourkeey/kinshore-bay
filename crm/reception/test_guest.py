from datetime import timedelta
from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone
from .models import Apartment, ApartmentType, StayRequest
from .services import _create_request, _change_status


class GuestRouteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.start = timezone.localdate() + timedelta(days=30)
        cls.end = cls.start + timedelta(days=2)
        cls.unit = Apartment.objects.get(code="A-102")
        stay = _create_request(cls.unit.pk, cls.start, cls.end, 4)
        _change_status(stay.pk, "confirmed")

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.url = "/api/guest/stays/"
        self.csrf = self.client.get(self.url).json()["csrf"]
        self.data = {"category_id": "one", "checkin": self.start.isoformat(), "checkout": self.end.isoformat(),
                     "guests": 4, "nightly_cents": 13500}

    def send(self):
        return self.client.post(self.url, self.data, content_type="application/json", HTTP_X_CSRFTOKEN=self.csrf)

    def test_second_unit_retry_and_private_receipt(self):
        self.assertEqual(self.client.post(self.url, self.data, content_type="application/json").status_code, 403)
        result = self.send()
        self.assertEqual(result.status_code, 201)
        stay = StayRequest.objects.get(reference=result.json()["reference"])
        self.assertEqual(stay.apartment.code, "B-102")
        ApartmentType.objects.filter(code="one").update(nightly_cents=14950)
        self.assertEqual(self.send().json()["reference"], stay.reference)
        self.data["nightly_cents"] = 14950
        self.assertEqual(self.send().json()["reference"], stay.reference)
        self.assertEqual(StayRequest.objects.filter(demo_submission__guest_owner__gt="").count(), 1)
        self.assertEqual(self.client.get(self.url).json()["stays"][0]["total_cents"], 27000)
        self.assertEqual(Client().get(self.url).json()["stays"], [])

    def test_changed_price_and_adjacent_dates(self):
        ApartmentType.objects.filter(code="one").update(nightly_cents=14550)
        self.assertEqual(self.send().status_code, 409)
        self.data.update(checkin=self.end.isoformat(), checkout=(self.end + timedelta(days=2)).isoformat(), nightly_cents=14550)
        quotes = self.client.get("/api/guest/quotes/", self.data).json()["rooms"]
        self.assertEqual(next(r for r in quotes if r["id"] == "one")["total_cents"], 29100)
        stay = StayRequest.objects.get(reference=self.send().json()["reference"])
        self.assertEqual(stay.apartment.code, "A-102")

    def test_sold_out_category(self):
        for unit in Apartment.objects.filter(category__code="one").exclude(pk=self.unit.pk):
            _change_status(_create_request(unit.pk, self.start, self.end, 4).pk, "confirmed")
        rows = self.client.get("/api/guest/quotes/", self.data).json()["rooms"]
        self.assertNotIn("one", [row["id"] for row in rows])
        self.assertEqual(self.send().status_code, 400)

    def test_arrival_details_are_valid_private_and_do_not_split_retries(self):
        for fields in ({"children": 4}, {"children": True}, {"with_pet": 1}, {"by_car": "yes"}):
            with self.subTest(fields=fields):
                original = self.data.copy()
                self.data.update(fields)
                self.assertEqual(self.send().status_code, 400)
                self.data = original
        self.data.update(children=2, with_pet=True, by_car=False)
        first = self.send()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(self.send().json()["reference"], first.json()["reference"])
        receipt, = self.client.get(self.url).json()["stays"]
        self.assertEqual((receipt["children"], receipt["with_pet"], receipt["by_car"]), (2, True, False))
        self.assertEqual(Client().get(self.url).json()["stays"], [])
        self.data["by_car"] = True
        self.assertEqual(self.send().status_code, 409)
