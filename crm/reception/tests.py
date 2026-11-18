from datetime import date
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import CommandError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from .models import Apartment, StayRequest
from .access import OWNER_GROUP, RECEPTION_GROUP, setup_demo_roles
from .services import change_status, create_request, list_apartments, list_requests, require_owner_analytics

class ReceptionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        setup_demo_roles()
        cls.receptionist = get_user_model().objects.create_user(username="test_reception")
        cls.receptionist.groups.add(Group.objects.get(name=RECEPTION_GROUP))

    def create_request(self, *args, **kwargs):
        return create_request(*args, actor=self.receptionist, **kwargs)

    def change_status(self, *args, **kwargs):
        return change_status(*args, actor=self.receptionist, **kwargs)

    def test_demo_seed_is_repeatable_and_preserves_status(self):
        self.assertEqual(Apartment.objects.count(), 15)
        self.assertEqual(StayRequest.objects.count(), 3)
        existing = StayRequest.objects.get(reference="demo-02")
        self.change_status(existing.pk, "cancelled")
        call_command("seed_demo", verbosity=0)
        existing.refresh_from_db()
        self.assertEqual(existing.status, "cancelled")
        self.assertEqual(StayRequest.objects.count(), 3)

    def test_overlapping_confirmations_and_adjacent_stay(self):
        unit = Apartment.objects.get(code="D-101")
        first = self.create_request(unit.pk, date(2030, 2, 1), date(2030, 2, 5), 2)
        conflict = self.create_request(unit.pk, date(2030, 2, 4), date(2030, 2, 7), 2)
        adjacent = self.create_request(unit.pk, date(2030, 2, 5), date(2030, 2, 7), 2)
        self.change_status(first.pk, "confirmed")
        with self.assertRaises(ValidationError):
            self.change_status(conflict.pk, "confirmed")
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "requested")
        self.change_status(adjacent.pk, "confirmed")
        adjacent.refresh_from_db()
        self.assertEqual(adjacent.status, "confirmed")

    def test_dates_capacity_and_state_transitions(self):
        unit = Apartment.objects.get(code="E-101")
        for checkin, checkout, guests in ((date(2030, 1, 1), date(2030, 1, 1), 1),
                                          (date(2030, 1, 1), date(2030, 5, 1), 1),
                                          (date(2030, 1, 1), date(2030, 1, 3), 0),
                                          (date(2030, 1, 1), date(2030, 1, 3), 3)):
            with self.subTest(checkin=checkin, checkout=checkout, guests=guests), self.assertRaises(ValidationError):
                self.create_request(unit.pk, checkin, checkout, guests)
        request = self.create_request(unit.pk, date(2030, 5, 1), date(2030, 5, 5), 2)
        with self.assertRaises(ValidationError):
            self.change_status(request.pk, "checked_out")
        for status in ("confirmed", "checked_in", "checked_out"):
            self.change_status(request.pk, status)
        with self.assertRaises(ValidationError):
            self.change_status(request.pk, "cancelled")

    def test_cancellation_frees_dates_and_price_is_snapshotted(self):
        unit = Apartment.objects.select_related("category").get(code="D-102")
        first = self.create_request(unit.pk, date(2030, 4, 1), date(2030, 4, 5), 2)
        second = self.create_request(unit.pk, date(2030, 4, 2), date(2030, 4, 4), 2)
        old_price = first.nightly_cents
        unit.category.nightly_cents += 1000
        unit.category.save(update_fields=["nightly_cents"])
        first.refresh_from_db()
        self.assertEqual(first.nightly_cents, old_price)
        self.change_status(first.pk, "confirmed")
        self.change_status(first.pk, "cancelled")
        self.change_status(second.pk, "confirmed")

    def test_database_check_constraint_rejects_invalid_dates(self):
        unit = Apartment.objects.get(code="E-101")
        with self.assertRaises(IntegrityError), transaction.atomic():
            StayRequest.objects.create(reference="invalid", apartment=unit, checkin=date(2030, 1, 5),
                                       checkout=date(2030, 1, 5), guests=1, nightly_cents=100)

class AccessTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        setup_demo_roles()
        User = get_user_model()
        cls.receptionist = User.objects.create_user(username="demo_receptionist")
        cls.receptionist.groups.add(Group.objects.get(name=RECEPTION_GROUP))
        cls.owner = User.objects.create_user(username="demo_owner")
        cls.owner.groups.add(Group.objects.get(name=OWNER_GROUP))
        cls.unassigned = User.objects.create_user(username="demo_unassigned")
        cls.inactive = User.objects.create_user(username="demo_inactive", is_active=False)
        cls.inactive.groups.add(Group.objects.get(name=RECEPTION_GROUP))

    def test_reception_can_read_create_and_change_but_not_analytics(self):
        self.assertEqual(list_requests(actor=self.receptionist).count(), 3)
        self.assertEqual(list_apartments(actor=self.receptionist).count(), 15)
        unit = Apartment.objects.get(code="E-101")
        request = create_request(unit.pk, date(2030, 6, 1), date(2030, 6, 3), 2, actor=self.receptionist)
        change_status(request.pk, "confirmed", actor=self.receptionist)
        request.refresh_from_db()
        self.assertEqual(request.status, "confirmed")
        with self.assertRaises(PermissionDenied):
            require_owner_analytics(actor=self.receptionist)
        self.assertFalse(self.receptionist.has_perm("reception.delete_stayrequest"))

    def test_owner_can_read_and_use_analytics_permission_but_not_modify(self):
        self.assertEqual(list_requests(actor=self.owner).count(), 3)
        self.assertEqual(list_apartments(actor=self.owner).count(), 15)
        require_owner_analytics(actor=self.owner)
        unit = Apartment.objects.get(code="E-101")
        request = StayRequest.objects.get(reference="demo-02")
        with self.assertRaises(PermissionDenied):
            create_request(unit.pk, date(2030, 6, 1), date(2030, 6, 3), 2, actor=self.owner)
        with self.assertRaises(PermissionDenied):
            change_status(request.pk, "confirmed", actor=self.owner)
        request.refresh_from_db()
        self.assertEqual(request.status, "requested")

    def test_anonymous_unassigned_and_inactive_have_no_service_access(self):
        unit = Apartment.objects.get(code="E-101")
        request = StayRequest.objects.get(reference="demo-02")
        for actor in (None, AnonymousUser(), self.unassigned, self.inactive):
            with self.subTest(actor=str(actor)):
                with self.assertRaises(PermissionDenied):
                    list_requests(actor=actor)
                with self.assertRaises(PermissionDenied):
                    list_apartments(actor=actor)
                with self.assertRaises(PermissionDenied):
                    create_request(unit.pk, date(2030, 6, 1), date(2030, 6, 3), 2, actor=actor)
                with self.assertRaises(PermissionDenied):
                    change_status(request.pk, "confirmed", actor=actor)
                with self.assertRaises(PermissionDenied):
                    require_owner_analytics(actor=actor)

    def test_setup_is_repeatable_and_never_overwrites_changed_groups(self):
        setup_demo_roles()
        group = Group.objects.get(name=RECEPTION_GROUP)
        extra = Permission.objects.get(content_type__app_label="auth", codename="add_user")
        group.permissions.add(extra)
        with self.assertRaises(CommandError):
            setup_demo_roles()
        self.assertTrue(group.permissions.filter(pk=extra.pk).exists())
