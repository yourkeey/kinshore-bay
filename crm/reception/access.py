"""Demo role policy and permission checks for server-side service entry points."""
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.core.management.base import CommandError
from django.db import transaction

RECEPTION_GROUP = "kinshore_reception"
OWNER_GROUP = "kinshore_owner"
COMMON = {"view_building", "view_apartmenttype", "view_apartment", "view_stayrequest"}
ROLE_PERMISSIONS = {
    RECEPTION_GROUP: COMMON | {"add_stayrequest", "change_stayrequest"},
    OWNER_GROUP: COMMON | {"view_owner_analytics"},
}

def require_permission(actor, codename):
    if not (actor and actor.is_authenticated and actor.is_active and actor.has_perm(f"reception.{codename}")):
        raise PermissionDenied("You do not have permission to perform this action.")

@transaction.atomic
def setup_demo_roles():
    """Create the named groups once; reject pre-existing groups with different rights."""
    for name, codenames in ROLE_PERMISSIONS.items():
        permissions = list(Permission.objects.filter(content_type__app_label="reception", codename__in=codenames))
        if {permission.codename for permission in permissions} != codenames:
            raise CommandError("Required permissions are missing. Run database migrations first.")
        group, created = Group.objects.get_or_create(name=name)
        if created:
            group.permissions.add(*permissions)
            continue
        actual = set(group.permissions.values_list("content_type__app_label", "codename"))
        expected = {("reception", codename) for codename in codenames}
        if actual != expected:
            raise CommandError(f"Group {name} already exists with different permissions; it was not modified.")
