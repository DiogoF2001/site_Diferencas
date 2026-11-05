"""Permission engine: every access decision in the portal goes through this module.

Modules declare their permissions in a `permissions.py`, discovered when the app registry loads.
Views ask `has_perm_in(user, "salas.approve", location)` and never look at role names. Unknown
permission codes raise, so that a typo is a bug in the tests and not a silent refusal.
"""

import enum
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured
from django.db.models import QuerySet
from django.utils import timezone

from core.models import Location, Membership, Mentorship, Role, Subrole, User

ROLE_LEVELS = {Role.PROFESSIONAL: 1, Role.SECRETARIAT: 2, Role.COORDINATION: 3}

MANAGE_MEMBERS = "core.manage_members"


class AdminAccess(enum.Enum):
    FULL = "full"
    # The admin account has no bookings of its own, so it can only act in someone else's name.
    ON_BEHALF = "on_behalf"


@dataclass(frozen=True)
class PermissionRule:
    roles: frozenset = frozenset()
    admin: AdminAccess = AdminAccess.FULL
    # Global permissions apply to the whole system, so only the admin can hold them.
    is_global: bool = False
    # What the person named by the admin must hold; by default, this same permission.
    on_behalf_needs: str | None = None


_registry: dict[str, PermissionRule] = {}


def register_permissions(module, rules):
    """Declare a module's permissions, as {"approve": PermissionRule(...)} under `module.`."""
    for name, rule in rules.items():
        code = f"{module}.{name}"
        if code in _registry:
            raise ImproperlyConfigured(f"Permission declared twice: {code}")
        if rule.is_global and rule.roles:
            raise ImproperlyConfigured(f"A global permission cannot be given to roles: {code}")
        _registry[code] = rule


def registered_permissions():
    return frozenset(_registry)


def _rule(perm):
    try:
        return _registry[perm]
    except KeyError:
        raise ImproperlyConfigured(f"Unknown permission: {perm}") from None


def is_admin(user):
    return user.is_authenticated and user.is_active and user.is_superuser


def _can_hold_memberships(user):
    """The admin is a technical account: a stray membership row must not change what it can do."""
    return user.is_authenticated and user.is_active and not user.is_superuser


def _active_roles(user, location):
    if not _can_hold_memberships(user) or not location.is_active:
        return set()
    memberships = Membership.objects.active_on().filter(user=user, location=location)
    return set(memberships.values_list("role", flat=True))


def has_perm_in(user, perm, location=None, *, on_behalf_of=None):
    """Whether `user` holds `perm` in `location`, counting only memberships active today in Lisbon.

    With `on_behalf_of`, whether the admin can use `perm` in that person's name. Nobody else acts
    in another person's name: the secretariat books directly for others under its own permission.
    """
    rule = _rule(perm)
    if location is None and not rule.is_global:
        raise ValueError(f"{perm} needs a location")
    if on_behalf_of is not None:
        return _can_act_on_behalf(user, rule, on_behalf_of) and has_perm_in(
            on_behalf_of, rule.on_behalf_needs or perm, location
        )
    if is_admin(user):
        return rule.admin is AdminAccess.FULL
    if rule.is_global:
        return False
    return bool(_active_roles(user, location) & rule.roles)


def _can_act_on_behalf(user, rule, on_behalf_of):
    return is_admin(user) and rule.admin is AdminAccess.ON_BEHALF and not on_behalf_of.is_superuser


def locations_with_perm(user, perm, *, on_behalf_of=None) -> QuerySet:
    """The locations where `has_perm_in` is true for these arguments."""
    rule = _rule(perm)
    if rule.is_global:
        raise ValueError(f"{perm} does not depend on a location")
    if on_behalf_of is not None:
        if not _can_act_on_behalf(user, rule, on_behalf_of):
            return Location.objects.none()
        return locations_with_perm(on_behalf_of, rule.on_behalf_needs or perm)
    if is_admin(user):
        return Location.objects.all() if rule.admin is AdminAccess.FULL else Location.objects.none()
    if not _can_hold_memberships(user):
        return Location.objects.none()
    memberships = Membership.objects.active_on().filter(user=user, role__in=rule.roles)
    return Location.objects.filter(is_active=True, pk__in=memberships.values("location"))


def filter_by_perm(queryset, user, perm, *, location_field="location", on_behalf_of=None):
    """Keep only the rows from locations where `user` holds `perm`."""
    locations = locations_with_perm(user, perm, on_behalf_of=on_behalf_of)
    return queryset.filter(**{f"{location_field}__in": locations})


def role_level_in(user, location):
    """The user's highest active level in the location; 0 without an active membership."""
    return max((ROLE_LEVELS[role] for role in _active_roles(user, location)), default=0)


def can_assign_role(actor, role, location):
    """Roles can only be given up to the actor's own level in that location."""
    level = ROLE_LEVELS[Role(role)]
    if is_admin(actor):
        return True
    return has_perm_in(actor, MANAGE_MEMBERS, location) and level <= role_level_in(actor, location)


def assignable_roles(actor, location):
    return [role for role in Role if can_assign_role(actor, role, location)]


def can_remove_from_location(actor, target, location):
    """Removing someone also needs the actor's level, counting the roles that have yet to start."""
    today = timezone.localdate()
    roles = Membership.objects.filter(user=target, location=location).overlapping(today)
    levels = [ROLE_LEVELS[role] for role in roles.values_list("role", flat=True)]
    if not levels:
        return False
    if is_admin(actor):
        return True
    return has_perm_in(actor, MANAGE_MEMBERS, location) and max(levels) <= role_level_in(
        actor, location
    )


def can_manage_account(actor, target):
    """Deactivating an account or resetting its 2FA: a level >= the target's in all their locations.

    Their locations are the ones with an active or future membership, so that an account can be
    managed before it starts and no one acts on a person about to outrank them elsewhere. A person
    never does this to their own account, because a stolen session could then remove the 2FA.
    Someone whose memberships have all ended is in no location, so only the admin can act.
    """
    if actor.pk == target.pk:
        return False
    if is_admin(actor):
        return True
    if target.is_superuser:
        return False
    # From the rows, not from role_level_in: a deactivated account keeps the level it had.
    target_levels = {}
    memberships = Membership.objects.filter(user=target).overlapping(timezone.localdate())
    for location_id, role in memberships.values_list("location_id", "role"):
        target_levels[location_id] = max(target_levels.get(location_id, 0), ROLE_LEVELS[role])
    if not target_levels:
        return False
    locations = Location.objects.filter(pk__in=target_levels)
    return all(
        has_perm_in(actor, MANAGE_MEMBERS, location)
        and target_levels[location.pk] <= role_level_in(actor, location)
        for location in locations
    )


def mentees_of(user, location) -> QuerySet:
    """The people `user` mentors in `location`, while both memberships and the relation are active.

    A mentorship never reaches other locations, even when the same two people are also there.
    """
    if not _can_hold_memberships(user) or not location.is_active:
        return User.objects.none()
    today = timezone.localdate()
    professionals = Membership.objects.active_on(today).filter(
        location=location, role=Role.PROFESSIONAL
    )
    if not professionals.filter(user=user).exists():
        return User.objects.none()
    mentorships = Mentorship.objects.active_on(today).filter(mentor=user, location=location)
    return User.objects.filter(
        is_active=True,
        pk__in=mentorships.values("mentee"),
    ).filter(pk__in=professionals.filter(subrole=Subrole.INTERN).values("user"))


register_permissions(
    "core",
    {
        # Create accounts and give roles in the location; the ceiling is in can_assign_role.
        "manage_members": PermissionRule(roles=frozenset({Role.SECRETARIAT, Role.COORDINATION})),
        "manage_mentorships": PermissionRule(
            roles=frozenset({Role.SECRETARIAT, Role.COORDINATION})
        ),
        # The location's professionals, with their roles here and, optionally, elsewhere.
        "view_professionals": PermissionRule(roles=frozenset({Role.COORDINATION})),
        "view_audit": PermissionRule(roles=frozenset({Role.COORDINATION})),
        "technical_area": PermissionRule(is_global=True),
    },
)
