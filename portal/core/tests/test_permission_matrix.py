"""Role × permission × scope, for the permissions of the core. Expectations come from the plan."""

import pytest

from core.models import Location, Role
from core.permissions import has_perm_in, locations_with_perm
from core.tests.helpers import make_account, make_member

pytestmark = pytest.mark.django_db

ROLES = list(Role)

# Permission → the roles that hold it. The admin is covered below.
CORE_MATRIX = {
    "core.manage_members": {Role.SECRETARIAT, Role.COORDINATION},
    "core.manage_mentorships": {Role.SECRETARIAT, Role.COORDINATION},
    "core.view_professionals": {Role.COORDINATION},
    "core.view_audit": {Role.COORDINATION},
}


@pytest.fixture
def location():
    return Location.objects.create(name="Polo A")


@pytest.fixture
def other_location():
    return Location.objects.create(name="Polo B")


@pytest.mark.parametrize("perm,holders", CORE_MATRIX.items())
@pytest.mark.parametrize("role", ROLES)
def test_role_in_the_same_location(perm, holders, role, location):
    user = make_account("pessoa")
    make_member(user, location, role)

    assert has_perm_in(user, perm, location) is (role in holders)
    assert (location in locations_with_perm(user, perm)) is (role in holders)


@pytest.mark.parametrize("perm", CORE_MATRIX)
@pytest.mark.parametrize("role", ROLES)
def test_role_in_another_location_gives_nothing(perm, role, location, other_location):
    user = make_account("pessoa")
    make_member(user, other_location, role)

    assert has_perm_in(user, perm, location) is False
    assert location not in locations_with_perm(user, perm)


@pytest.mark.parametrize("perm", CORE_MATRIX)
@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize(
    "start,end", [pytest.param(-30, -1, id="expired"), pytest.param(1, 30, id="not_started")]
)
def test_membership_outside_its_dates_gives_nothing(perm, role, start, end, location):
    user = make_account("pessoa")
    make_member(user, location, role, start=start, end=end)

    assert has_perm_in(user, perm, location) is False
    assert not locations_with_perm(user, perm).exists()


@pytest.mark.parametrize("perm", CORE_MATRIX)
def test_admin_holds_every_core_permission_everywhere(perm, location):
    admin = make_account("admin", is_superuser=True)

    assert has_perm_in(admin, perm, location) is True
    assert location in locations_with_perm(admin, perm)


def test_technical_area_is_only_for_the_admin(location):
    admin = make_account("admin", is_superuser=True)
    assert has_perm_in(admin, "core.technical_area") is True

    for role in ROLES:
        user = make_account(role)
        make_member(user, location, role)
        assert has_perm_in(user, "core.technical_area") is False
