from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from reception.models import DemoSubmission, GrillBooking, StayRequest, WalkBooking, WalkSession


class Command(BaseCommand):
    help = "Remove expired public workspaces and expired Django sessions."

    @transaction.atomic
    def handle(self, *args, **options):
        if not getattr(settings, "PUBLIC_DEMO", False):
            raise CommandError("Use the dedicated public demo settings.")
        cutoff = timezone.localdate() - timedelta(days=1)
        # Sessions last one day. A workspace created before yesterday has expired.
        expired = {"workspace__gt": "", "workspace__lt": f"{cutoff:%Y%m%d}-"}
        stays = StayRequest.objects.filter(**expired)
        DemoSubmission.objects.filter(stay__in=stays).delete()
        GrillBooking.objects.filter(stay__in=stays).delete()
        WalkBooking.objects.filter(stay__in=stays).delete()
        deleted, _ = stays.delete()
        WalkSession.objects.filter(**expired).delete()
        Session.objects.filter(expire_date__lte=timezone.now()).delete()
        self.stdout.write(f"Removed {deleted} expired stay and history records.")
