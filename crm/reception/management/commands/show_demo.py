from django.core.management.base import BaseCommand
from reception.models import Apartment, StayRequest

class Command(BaseCommand):
    help = "Show the local fictional reception data."

    def handle(self, *args, **options):
        self.stdout.write(f"DEMO DATA · {Apartment.objects.count()} apartments · fictional resort\n")
        for item in StayRequest.objects.select_related("apartment").order_by("checkin", "reference"):
            self.stdout.write(f"{item.reference:12} {item.apartment.code:6} {item.checkin} → {item.checkout}  {item.guests} guest(s)  {item.status}")
