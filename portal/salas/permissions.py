"""Permissions of the rooms module, from the table in section 4 of the plan."""

from django.db.models import Q

from core.models import Role, User
from core.permissions import (
    AdminAccess,
    PermissionRule,
    has_perm_in,
    mentees_of,
    register_permissions,
)

EVERYONE = frozenset(Role)
STAFF = frozenset({Role.SECRETARIAT, Role.COORDINATION})

register_permissions(
    "salas",
    {
        "view_availability": PermissionRule(roles=EVERYONE),
        # Details and history of all bookings. Holders and participants see their own bookings
        # through the booking itself, not through this permission.
        "view_all_bookings": PermissionRule(roles=STAFF),
        "submit_request": PermissionRule(
            roles=frozenset({Role.PROFESSIONAL}), admin=AdminAccess.ON_BEHALF
        ),
        # Whoever the booking is for only needs to be in the location: they do not book directly.
        "book_directly": PermissionRule(
            roles=STAFF, admin=AdminAccess.ON_BEHALF, on_behalf_needs="salas.view_availability"
        ),
        "add_participants": PermissionRule(roles=EVERYONE, admin=AdminAccess.ON_BEHALF),
        "approve": PermissionRule(roles=STAFF),
        "change_any_booking": PermissionRule(roles=STAFF),
        # Rooms, exclusive assignments, closures and the location's rules.
        "manage_location": PermissionRule(roles=STAFF),
        "override_holidays": PermissionRule(roles=STAFF),
        "view_reports": PermissionRule(roles=frozenset({Role.COORDINATION})),
        # Section 6: only the admin switches on the release of exclusive rooms.
        "enable_room_release": PermissionRule(),
    },
)


def _visible_people(viewer, location, whole_location_perm):
    if has_perm_in(viewer, whole_location_perm, location):
        # Not only the active members: past interns' hours still count in the location's reports.
        return User.objects.filter(memberships__location=location).distinct()
    if not has_perm_in(viewer, "salas.view_availability", location):
        return User.objects.none()
    return User.objects.filter(
        Q(pk=viewer.pk) | Q(pk__in=mentees_of(viewer, location).values("pk"))
    )


def people_with_visible_schedule(viewer, location):
    """Whose schedule `viewer` can see in `location`: their own, their mentees', or all (staff)."""
    return _visible_people(viewer, location, "salas.view_all_bookings")


def people_with_visible_hours(viewer, location):
    """Whose hours `viewer` can see in `location`: their own, their mentees', or all (reports).

    The holder of a booking also sees its participants' hours, through that booking (task 10).
    """
    return _visible_people(viewer, location, "salas.view_reports")
