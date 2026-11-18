from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from reception.access import RECEPTION_GROUP, setup_demo_roles


class Command(BaseCommand):
    help = "Create a local staff account with reception permissions."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, username, **options):
        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            raise CommandError("That username already exists.")
        user = user_model(username=username)
        password = getpass("Password: ")
        if not password or password != getpass("Password again: "):
            raise CommandError("Enter matching non-empty passwords.")
        try:
            user.full_clean(exclude=["password"])
            validate_password(password, user=user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc

        with transaction.atomic():
            setup_demo_roles()
            user.set_password(password)
            user.save()
            user.groups.add(Group.objects.get(name=RECEPTION_GROUP))
        self.stdout.write(self.style.SUCCESS("Reception user created."))
