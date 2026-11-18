import json
import os
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import Client, TestCase

from .models import DemoSubmission, StayRequest

TOKEN = "t" * 43  # Synthetic value used only by tests.
ENDPOINT = "/api/internal/demo-requests/"
PAYLOAD = {"apartment_code": "A-101", "checkin": "2030-06-10", "checkout": "2030-06-14", "guests": 2}

class DemoIntakeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.service_user = get_user_model().objects.create_user(username="test_machine")
        permission = Permission.objects.get(content_type__app_label="reception", codename="add_stayrequest")
        cls.service_user.user_permissions.add(permission)

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.key = str(uuid4())
        self.config = patch.dict(os.environ, {"KINSHORE_CRM_TOKEN": TOKEN, "KINSHORE_CRM_USER": "test_machine"})
        self.config.start()
        self.addCleanup(self.config.stop)

    def post(self, data=None, *, key=None, token=TOKEN, content_type="application/json"):
        return self.client.post(ENDPOINT, data=json.dumps(PAYLOAD if data is None else data), content_type=content_type,
                                HTTP_AUTHORIZATION=f"Bearer {token}", HTTP_IDEMPOTENCY_KEY=key or self.key)

    def test_creates_once_and_duplicate_returns_same_reference(self):
        before = StayRequest.objects.count()
        first = self.post()
        self.assertEqual(first.status_code, 201)
        self.assertTrue(first.json()["demo"])
        self.assertEqual(first.json()["status"], "requested")
        self.assertEqual(first["Cache-Control"], "no-store")
        self.assertEqual(StayRequest.objects.count(), before + 1)
        second = self.post()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["reference"], first.json()["reference"])
        self.assertEqual(StayRequest.objects.count(), before + 1)
        self.assertEqual(DemoSubmission.objects.count(), 1)

    def test_reusing_key_with_different_payload_returns_conflict(self):
        self.assertEqual(self.post().status_code, 201)
        changed = {**PAYLOAD, "checkout": "2030-06-15"}
        self.assertEqual(self.post(changed).status_code, 409)
        self.assertEqual(DemoSubmission.objects.count(), 1)

    def test_category_request_creates_request_for_matching_demo_unit(self):
        data = {"category_id": "one", "checkin": "2030-06-10", "checkout": "2030-06-14", "guests": 4}
        result = self.post(data)
        self.assertEqual(result.status_code, 201)
        stay = StayRequest.objects.select_related("apartment__category").get(reference=result.json()["reference"])
        self.assertEqual(stay.apartment.category.code, "one")
        self.assertEqual(stay.status, "requested")
        self.assertEqual(self.post(data).json()["reference"], stay.reference)
        self.assertEqual(self.post({**data, "category_id": "studio"}).status_code, 409)

    def test_category_and_unit_cannot_be_submitted_together(self):
        self.assertEqual(self.post({**PAYLOAD, "category_id": "studio"}).status_code, 400)
        self.assertEqual(DemoSubmission.objects.count(), 0)

    def test_missing_or_invalid_auth_fails_without_creating_records(self):
        before = StayRequest.objects.count()
        self.assertEqual(self.post(token="wrong" * 9).status_code, 401)
        self.assertEqual(self.client.post(ENDPOINT, data="{}", content_type="application/json").status_code, 401)
        with patch.dict(os.environ, {"KINSHORE_CRM_TOKEN": ""}):
            self.assertEqual(self.post().status_code, 503)
        self.assertEqual(StayRequest.objects.count(), before)
        self.assertEqual(DemoSubmission.objects.count(), 0)

    def test_machine_user_must_have_only_create_permission_and_no_password(self):
        extra = Permission.objects.get(content_type__app_label="reception", codename="change_stayrequest")
        self.service_user.user_permissions.add(extra)
        self.assertEqual(self.post().status_code, 503)
        self.service_user.user_permissions.remove(extra)
        self.service_user.set_password("not-used-for-a-real-account")
        self.service_user.save(update_fields=["password"])
        self.assertEqual(self.post().status_code, 503)
        self.assertEqual(DemoSubmission.objects.count(), 0)

    def test_validation_failure_rolls_back_and_key_can_be_retried(self):
        before = StayRequest.objects.count()
        for data in ({**PAYLOAD, "guests": True}, {**PAYLOAD, "guests": 3},
                     {**PAYLOAD, "checkout": "2030-06-10"}, {**PAYLOAD, "apartment_code": "unknown"},
                     {**PAYLOAD, "email": "not-accepted"}):
            with self.subTest(data=data):
                self.assertEqual(self.post(data).status_code, 400)
        self.assertEqual(self.post(key="not-a-uuid").status_code, 400)
        self.assertEqual(self.post(content_type="text/plain").status_code, 400)
        self.assertEqual(StayRequest.objects.count(), before)
        self.assertEqual(DemoSubmission.objects.count(), 0)
        self.assertEqual(self.post().status_code, 201)

    def test_only_post_is_allowed_and_large_payload_is_rejected(self):
        self.assertEqual(self.client.get(ENDPOINT).status_code, 405)
        result = self.client.post(ENDPOINT, data=" " * 5000, content_type="application/json",
                                  HTTP_AUTHORIZATION=f"Bearer {TOKEN}", HTTP_IDEMPOTENCY_KEY=self.key)
        self.assertEqual(result.status_code, 400)
        self.assertEqual(DemoSubmission.objects.count(), 0)
