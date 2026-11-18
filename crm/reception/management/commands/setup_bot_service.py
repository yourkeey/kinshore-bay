import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Create or verify the least-privilege service identity for the Telegram bot."

    @transaction.atomic
    def handle(self, *args, **options):
        username = os.environ.get("KINSHORE_CRM_USER", "")
        if not username:
            raise CommandError("Set KINSHORE_CRM_USER first.")
        user_model = get_user_model()
        actor = user_model.objects.filter(username=username).first()
        if actor is None:
            actor = user_model.objects.create_user(username=username)
            actor.user_permissions.add(Permission.objects.get(
                content_type__app_label="reception", codename="add_stayrequest",
            ))
        if (not actor.is_active or actor.is_superuser or actor.is_staff
                or actor.has_usable_password() or actor.get_all_permissions() != {"reception.add_stayrequest"}):
            raise CommandError("The existing account does not match the bot service role.")
        self.stdout.write(self.style.SUCCESS("Bot service identity ready."))
