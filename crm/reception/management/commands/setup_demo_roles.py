from django.core.management.base import BaseCommand
from reception.access import setup_demo_roles

class Command(BaseCommand):
    help = "Create or verify the two local demo role groups, without creating users."

    def handle(self, *args, **options):
        setup_demo_roles()
        self.stdout.write(self.style.SUCCESS("Reception and owner groups are ready. No user accounts were created."))
