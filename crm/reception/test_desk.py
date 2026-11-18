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
from .models import Apartment, StatusChange, StayRequest
from .services import _create_request, change_status


class DeskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        setup_demo_roles()
        cls.staff = get_user_model().objects.create_user("desk-test")
        cls.staff.groups.add(Group.objects.get(name=RECEPTION_GROUP))
        cls.viewer = get_user_model().objects.create_user("owner-test")
        cls.viewer.groups.add(Group.objects.get(name=OWNER_GROUP))

    def test_confirmation_conflict_reassignment_and_cancellation_reach_guest(self):
        # Submit through the public endpoint as a separate guest browser.
        guest = Client(enforce_csrf_checks=True)
        guest_url = "/api/guest/stays/"
        csrf = guest.get(guest_url).json()["csrf"]
        start = timezone.localdate()
        end = start + timedelta(days=2)
        receipt = guest.post(guest_url, {
            "category_id": "one", "checkin": start.isoformat(), "checkout": end.isoformat(),
            "nightly_cents": 13500, "guests": 4,
        }, content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(receipt.status_code, 201)
        reference = receipt.json()["reference"]
        stay = StayRequest.objects.get(reference=reference)
        blocker = _create_request(stay.apartment_id, start, end, 4)
        change_status(blocker.pk, "confirmed", actor=self.staff)
        detail_url = reverse("desk-detail", args=[reference])

        self.assertRedirects(self.client.get(detail_url), f"/reception/login/?next={detail_url}")
        self.client.force_login(self.viewer)
        self.assertNotContains(self.client.get(detail_url), "Cancel request")
        self.assertEqual(self.client.post(detail_url, {"status": "cancelled"}).status_code, 403)
        self.client.force_login(self.staff)
        today_url = reverse("desk-today")
        self.assertContains(self.client.get(today_url, {"q": reference.upper()}), reference)
        self.assertContains(self.client.get(today_url), blocker.reference)
        self.assertContains(self.client.get(today_url), reference)
        self.assertContains(self.client.get(detail_url), "already booked")
        stale = self.client.post(detail_url, {"status": "confirmed", "unit": stay.apartment.code})
        self.assertContains(stale, "already has a confirmed demo stay", status_code=409)

        alternative = Apartment.objects.get(code="B-102")
        self.assertRedirects(self.client.post(detail_url, {"status": "confirmed", "unit": alternative.code}), detail_url)
        guest_stay = guest.get(guest_url).json()["stays"][0]
        self.assertEqual(guest_stay["status"], "confirmed")
        self.assertEqual(guest_stay["building"], "B")
        change = StatusChange.objects.get(stay=stay)
        self.assertEqual((change.actor, change.previous, change.current), (self.staff, "requested", "confirmed"))
        self.assertEqual((change.previous_unit, change.current_unit), (stay.apartment.code, alternative.code))
        calendar_url = reverse("desk-calendar")
        self.assertContains(self.client.get(calendar_url, {"start": start}), f'href="{detail_url}"', count=2)
        self.assertNotContains(self.client.get(calendar_url, {"start": end}), reference)
        self.assertRedirects(self.client.post(detail_url, {"status": "cancelled"}), detail_url)
        self.assertEqual(guest.get(guest_url).json()["stays"][0]["status"], "cancelled")
        self.assertNotContains(self.client.get(calendar_url, {"start": start}), reference)

    def test_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        self.assertEqual(client.post(reverse("desk-detail", args=["demo-02"]), {"status": "confirmed"}).status_code, 403)


class ConfirmationRaceTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_only_one_staff_confirmation_takes_last_room(self):
        call_command("seed_demo", verbosity=0)
        setup_demo_roles()
        staff = get_user_model().objects.create_user("shift-staff")
        staff.groups.add(Group.objects.get(name=RECEPTION_GROUP))
        start = timezone.localdate() + timedelta(days=30)
        end = start + timedelta(days=2)
        units = list(Apartment.objects.filter(category__code="one").order_by("code"))
        last = units[0]
        for unit in units[1:]:
            blocker = _create_request(unit.pk, start, end, 4)
            change_status(blocker.pk, "confirmed", actor=staff)

        stays = [_create_request(last.pk, start, end, 4) for _ in range(2)]
        clients = [Client(), Client()]
        for client in clients:
            client.force_login(staff)

        ready = Barrier(2)

        def race_for_apartment_lock(execute, sql, params, many, context):
            if 'FROM "reception_apartment"' in sql and "FOR UPDATE" in sql:
                ready.wait(timeout=10)
            return execute(sql, params, many, context)

        def confirm(client, reference):
            try:
                with connection.execute_wrapper(race_for_apartment_lock):
                    response = client.post(reverse("desk-detail", args=[reference]),
                                           {"status": "confirmed", "unit": last.code})
                return response.status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as workers:
            jobs = [workers.submit(confirm, client, stay.reference) for client, stay in zip(clients, stays)]
            self.assertEqual(sorted(job.result(timeout=20) for job in jobs), [302, 409])
        statuses = StayRequest.objects.filter(pk__in=[stay.pk for stay in stays]).values_list("status", flat=True)
        self.assertCountEqual(statuses, ["confirmed", "requested"])
        self.assertEqual(StatusChange.objects.filter(stay__in=stays).count(), 1)
