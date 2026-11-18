"""Populate repeatable, fictional inventory without replacing existing records."""
from datetime import timedelta
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from reception.models import Apartment, ApartmentType, Building, StayRequest
from reception.services import _change_status, _create_request, available_units
from reception.walks import seed_walk_sessions

class Command(BaseCommand):
    help = "Add fictional apartments and requests for local CRM exploration."

    def add_arguments(self, parser):
        parser.add_argument("--shift", action="store_true", help="Add a fictional shift for today's date.")

    @transaction.atomic
    def handle(self, *args, **options):
        catalog_path = Path(__file__).resolve().parents[4] / "content" / "en.json"
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))["apartments"]
            by_code = {item["id"]: item for item in catalog}
            rows = [by_code[code] for code in ("studio", "one", "family")]
        except (OSError, ValueError, KeyError, TypeError):
            raise CommandError("Could not read the expected demo apartment categories.") from None

        apartments = {}
        for letter in "ABCDE":
            building, _ = Building.objects.get_or_create(code=letter)
            for index, item in enumerate(rows, start=1):
                category, _ = ApartmentType.objects.get_or_create(code=item["id"], defaults={
                    "name": item["name"], "capacity": item["guests"], "nightly_cents": item["price"] * 100})
                code = f"{letter}-10{index}"
                apartment, _ = Apartment.objects.get_or_create(code=code, defaults={"building": building, "category": category})
                apartments[code] = apartment

        today = timezone.localdate()
        seed_walk_sessions(today)
        sample_stays = [
            ("demo-01", "A-101", 2, 4, 2, True),
            ("demo-02", "B-102", 5, 7, 4, False),
            ("demo-03", "C-103", 8, 5, 6, False),
        ]
        if options["shift"]:
            day = today.strftime("%Y%m%d")
            sample_stays.extend([
                (f"arrival-{day}", "A-102", 0, 2, 4, True),
                (f"departure-{day}", "B-101", -2, 2, 2, True),
                (f"conflict-{day}", "A-102", 0, 2, 4, False),
            ])
        for reference, code, offset, nights, guests, confirmed in sample_stays:
            if StayRequest.objects.filter(reference=reference).exists():
                continue
            checkin = today + timedelta(days=offset)
            checkout = checkin + timedelta(days=nights)
            if confirmed and not available_units(checkin, checkout, guests).filter(pk=apartments[code].pk).exists():
                self.stdout.write(f"Skipped {reference}: {code} is already occupied.")
                continue
            request = _create_request(apartments[code].pk, checkin, checkout, guests, reference=reference)
            if confirmed:
                _change_status(request.pk, StayRequest.Status.CONFIRMED)
        self.stdout.write(self.style.SUCCESS("Demo data ready; existing records were preserved."))
        self.stdout.write("Fictional data only. No real reservations or payments.")
