from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from reception.access import setup_demo_roles
from reception.public_demo import DEMO_OPERATOR


class Command(BaseCommand):
    help = "Create the passwordless actor used by scoped public reception screens."

    @transaction.atomic
    def handle(self, *args, **options):
        if not getattr(settings, "PUBLIC_DEMO", False):
            raise CommandError("Use the dedicated public demo settings.")
        setup_demo_roles()
        group = Group.objects.get(name="kinshore_reception")
        users = get_user_model().objects
        actor = users.filter(username=DEMO_OPERATOR).first()
        if actor is None:
            actor = users.create_user(username=DEMO_OPERATOR)
            actor.groups.add(group)
        if (actor.has_usable_password() or not actor.is_active or actor.is_staff or actor.is_superuser
                or list(actor.groups.values_list("pk", flat=True)) != [group.pk]
                or actor.user_permissions.exists()):
            raise CommandError("The public demo actor does not match the reception role.")
