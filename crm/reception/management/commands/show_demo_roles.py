from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from reception.access import ROLE_PERMISSIONS

class Command(BaseCommand):
    help = "Show locally configured demo role permissions without listing users."

    def handle(self, *args, **options):
        for name in ROLE_PERMISSIONS:
            group = Group.objects.filter(name=name).first()
            if not group:
                raise CommandError("Demo roles are not set up. Run setup_demo_roles first.")
            permissions = group.permissions.select_related("content_type").order_by("content_type__app_label", "codename")
            self.stdout.write(name + ":")
            for item in permissions:
                self.stdout.write(f"  {item.content_type.app_label}.{item.codename}")
