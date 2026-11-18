from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .models import GrillBooking, StayRequest
from .public_demo import WORKSPACE_SESSION_KEY


@override_settings(
    ALLOWED_HOSTS=["kinshore.test", "192.0.2.10"],
    PUBLIC_DEMO_UPSTREAM_IP="192.0.2.10",
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    SECURE_SSL_REDIRECT=True,
    MIDDLEWARE=[
        "reception.public_demo.PublicDemoUpstreamMiddleware",
        "django.middleware.security.SecurityMiddleware",
    ],
)
class PublicDemoUpstreamTests(SimpleTestCase):
    def test_ip_serves_status_and_domain_uses_the_https_application(self):
        ip = "192.0.2.10:8876"
        response = self.client.get("/", HTTP_HOST=ip)
        self.assertContains(response, "Kinshore Bay backend is reachable.")
        self.assertFalse(response.cookies)
        self.assertEqual(self.client.head("/", HTTP_HOST=ip).status_code, 200)
        self.assertEqual(self.client.post("/", HTTP_HOST=ip).status_code, 405)
        self.assertEqual(self.client.get("/reception/", HTTP_HOST=ip).status_code, 404)
        self.assertEqual(self.client.get(
            "/reception/", HTTP_HOST="192.0.2.10.:8876", HTTP_X_FORWARDED_PROTO="https",
        ).status_code, 404)
        self.assertEqual(self.client.get("/", HTTP_HOST="other.test").status_code, 400)

        response = self.client.get("/", HTTP_HOST="kinshore.test")
        self.assertEqual(response["Location"], "https://kinshore.test/")
        response = self.client.get("/", HTTP_HOST="kinshore.test", HTTP_X_FORWARDED_PROTO="https")
        self.assertEqual(response["Location"], "/site/index.html")


@override_settings(PUBLIC_DEMO=True, MIDDLEWARE=[
    *settings.MIDDLEWARE, "reception.public_demo.PublicDemoMiddleware",
] if "reception.public_demo.PublicDemoMiddleware" not in settings.MIDDLEWARE else settings.MIDDLEWARE)
class PublicDemoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        call_command("setup_public_demo")
        today = timezone.localdate()
        cls.start = today + timedelta(days=(4 - today.weekday()) % 7 + 7)
        cls.saturday = cls.start + timedelta(days=1)
        cls.end = cls.start + timedelta(days=2)

    def submit(self, client):
        self.assertEqual(client.get("/site/miniapp.html").status_code, 200)
        csrf = client.get("/api/guest/stays/").json()["csrf"]
        reply = client.post("/api/guest/stays/", {
            "category_id": "one", "checkin": str(self.start), "checkout": str(self.end),
            "guests": 4, "nightly_cents": 13500,
        }, content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(reply.status_code, 201)
        return reply.json()["reference"], csrf

    def test_two_visitors_can_use_the_same_inventory_independently(self):
        first = Client(enforce_csrf_checks=True)
        second = Client(enforce_csrf_checks=True)
        a, csrf_a = self.submit(first)
        b, csrf_b = self.submit(second)
        self.assertNotEqual(a, b)
        detail = f"/reception/requests/{a}/"
        self.assertEqual(second.get(detail).status_code, 404)
        self.assertEqual(second.post(detail, {"status": "cancelled"}, HTTP_X_CSRFTOKEN=csrf_b).status_code, 404)
        self.assertNotContains(second.get("/reception/"), a)
        self.assertNotContains(first.get("/reception/"), b)
        self.assertEqual(first.post(detail, {"status": "confirmed", "unit": "A-102"}).status_code, 403)

        for client, reference, csrf in ((first, a, csrf_a), (second, b, csrf_b)):
            self.assertEqual(client.post(f"/reception/requests/{reference}/", {
                "status": "confirmed", "unit": "A-102",
            }, HTTP_X_CSRFTOKEN=csrf).status_code, 302)
            response = client.post("/reception/grills/", {
                "action": "reserve", "reference": reference, "day": str(self.saturday), "slot": 17, "table": 1,
            }, HTTP_X_CSRFTOKEN=csrf)
            self.assertEqual(response.status_code, 302)

        self.assertEqual(GrillBooking.objects.filter(day=self.saturday, slot=17, table=1).count(), 2)
        stays_a = first.get("/api/guest/stays/").json()["stays"]
        stays_b = second.get("/api/guest/stays/").json()["stays"]
        self.assertEqual([stay["reference"] for stay in stays_a], [a])
        self.assertEqual([stay["reference"] for stay in stays_b], [b])
        walk_a = stays_a[0]["walks"][0]["id"]
        walk_b = stays_b[0]["walks"][0]["id"]
        self.assertNotEqual(walk_a, walk_b)
        for client, reference, walk, csrf, expected in (
            (second, b, walk_a, csrf_b, 404), (first, a, walk_a, csrf_a, 200), (second, b, walk_b, csrf_b, 200),
        ):
            response = client.post(f"/api/guest/stays/{reference}/walks/{walk}/", {
                "adults": 4, "teens": 0, "children": 0,
            }, content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
            self.assertEqual(response.status_code, expected)
        self.assertEqual(first.post("/reception/walks/", {
            "action": "cancel", "day": str(self.saturday),
        }, HTTP_X_CSRFTOKEN=csrf_a).status_code, 302)
        self.assertFalse(second.get("/api/guest/stays/").json()["stays"][0]["walks"][0]["cancelled"])

    def test_expired_workspaces_are_removed_and_sign_out_splits_the_session(self):
        client = Client(enforce_csrf_checks=True)
        reference, csrf = self.submit(client)
        self.assertEqual(client.post("/reception/logout/", HTTP_X_CSRFTOKEN=csrf).status_code, 302)
        self.assertEqual(client.get("/reception/").status_code, 200)
        self.assertEqual(client.get(f"/reception/requests/{reference}/").status_code, 404)
        self.assertTrue(client.session[WORKSPACE_SESSION_KEY])
        StayRequest.objects.filter(reference=reference).update(workspace="20000101-expired")
        call_command("clear_public_demo")
        self.assertFalse(StayRequest.objects.filter(reference=reference).exists())
        self.assertTrue(StayRequest.objects.filter(workspace="").exists())
