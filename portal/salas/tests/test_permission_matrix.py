"""Role × permission × scope for the rooms module, written out from section 4 of the plan.

This repeats the table on purpose: if the declarations in salas/permissions.py drift from the plan,
these tests fail instead of following them.
"""

import pytest

from core.models import Location, Role
from core.permissions import (
    filter_by_perm,
    has_perm_in,
    locations_with_perm,
    registered_permissions,
)
from core.tests.helpers import make_account, make_member

pytestmark = pytest.mark.django_db

PROFESSIONAL, SECRETARIAT, COORDINATION = Role.PROFESSIONAL, Role.SECRETARIAT, Role.COORDINATION
STAFF = {SECRETARIAT, COORDINATION}
EVERYONE = set(Role)

# Permission → the roles that hold it.
MATRIX = {
    "salas.view_availability": EVERYONE,
    "salas.view_all_bookings": STAFF,
    "salas.submit_request": {PROFESSIONAL},
    "salas.book_directly": STAFF,
    "salas.add_participants": EVERYONE,
    "salas.approve": STAFF,
    "salas.change_any_booking": STAFF,
    "salas.manage_location": STAFF,
    "salas.override_holidays": STAFF,
    "salas.view_reports": {COORDINATION},
    "salas.enable_room_release": set(),
}
ADMIN_ON_BEHALF = {"salas.submit_request", "salas.book_directly", "salas.add_participants"}


@pytest.fixture
def location():
    return Location.objects.create(name="Polo A")


@pytest.fixture
def other_location():
    return Location.objects.create(name="Polo B")


def test_matrix_covers_every_permission_of_the_module():
    assert set(MATRIX) == {perm for perm in registered_permissions() if perm.startswith("salas.")}


@pytest.mark.parametrize("perm,holders", MATRIX.items())
@pytest.mark.parametrize("role", list(Role))
def test_role_in_the_same_location(perm, holders, role, location):
    user = make_account("pessoa")
    make_member(user, location, role)

    assert has_perm_in(user, perm, location) is (role in holders)
    assert (location in locations_with_perm(user, perm)) is (role in holders)


@pytest.mark.parametrize("perm", MATRIX)
@pytest.mark.parametrize("role", list(Role))
def test_role_in_another_location_gives_nothing(perm, role, location, other_location):
    user = make_account("pessoa")
    make_member(user, other_location, role)

    assert has_perm_in(user, perm, location) is False
    assert location not in locations_with_perm(user, perm)


@pytest.mark.parametrize("perm", MATRIX)
@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize(
    "start,end", [pytest.param(-30, -1, id="expired"), pytest.param(1, 30, id="not_started")]
)
def test_membership_outside_its_dates_gives_nothing(perm, role, start, end, location):
    user = make_account("pessoa")
    make_member(user, location, role, start=start, end=end)

    assert has_perm_in(user, perm, location) is False
    assert not locations_with_perm(user, perm).exists()


@pytest.mark.parametrize("perm", MATRIX)
def test_admin_acts_directly_except_where_the_plan_says_in_someone_elses_name(perm, location):
    admin = make_account("admin", is_superuser=True)
    direct = perm not in ADMIN_ON_BEHALF

    assert has_perm_in(admin, perm, location) is direct
    assert (location in locations_with_perm(admin, perm)) is direct


@pytest.mark.parametrize(
    "perm,principal_role,allowed",
    [
        ("salas.submit_request", PROFESSIONAL, True),
        # The secretariat and the coordination book directly; they do not submit requests.
        ("salas.submit_request", SECRETARIAT, False),
        ("salas.submit_request", COORDINATION, False),
        ("salas.add_participants", PROFESSIONAL, True),
        ("salas.add_participants", SECRETARIAT, True),
        ("salas.add_participants", COORDINATION, True),
        # Any member of the location can be the holder of a direct booking.
        ("salas.book_directly", PROFESSIONAL, True),
        ("salas.book_directly", SECRETARIAT, True),
        ("salas.book_directly", COORDINATION, True),
    ],
)
def test_admin_acts_in_the_name_of_a_person_in_the_location(
    perm, principal_role, allowed, location
):
    admin = make_account("admin", is_superuser=True)
    principal = make_account("pessoa")
    make_member(principal, location, principal_role)

    assert has_perm_in(admin, perm, location, on_behalf_of=principal) is allowed
    assert (location in locations_with_perm(admin, perm, on_behalf_of=principal)) is allowed


@pytest.mark.parametrize("perm", sorted(ADMIN_ON_BEHALF))
def test_admin_cannot_act_in_the_name_of_someone_from_another_location(
    perm, location, other_location
):
    admin = make_account("admin", is_superuser=True)
    principal = make_account("pessoa")
    make_member(principal, other_location, PROFESSIONAL)

    assert has_perm_in(admin, perm, location, on_behalf_of=principal) is False
    assert location not in locations_with_perm(admin, perm, on_behalf_of=principal)


@pytest.mark.parametrize("perm", sorted(ADMIN_ON_BEHALF))
def test_admin_cannot_act_in_the_name_of_someone_with_an_expired_membership(perm, location):
    admin = make_account("admin", is_superuser=True)
    principal = make_account("pessoa")
    make_member(principal, location, PROFESSIONAL, start=-30, end=-1)

    assert has_perm_in(admin, perm, location, on_behalf_of=principal) is False
    assert not locations_with_perm(admin, perm, on_behalf_of=principal).exists()


@pytest.mark.parametrize("perm", sorted(ADMIN_ON_BEHALF))
def test_admin_cannot_act_in_the_name_of_a_deactivated_account(perm, location):
    admin = make_account("admin", is_superuser=True)
    principal = make_account("pessoa", is_active=False)
    make_member(principal, location, PROFESSIONAL)

    assert has_perm_in(admin, perm, location, on_behalf_of=principal) is False


@pytest.mark.parametrize("perm", sorted(ADMIN_ON_BEHALF))
def test_admin_cannot_act_in_its_own_name(perm, location):
    admin = make_account("admin", is_superuser=True)

    assert has_perm_in(admin, perm, location, on_behalf_of=admin) is False
    assert not locations_with_perm(admin, perm, on_behalf_of=admin).exists()


@pytest.mark.parametrize("perm", sorted(ADMIN_ON_BEHALF))
def test_deactivated_admin_cannot_act_in_anyones_name(perm, location):
    admin = make_account("admin", is_superuser=True, is_active=False)
    principal = make_account("pessoa")
    make_member(principal, location, PROFESSIONAL)

    assert has_perm_in(admin, perm, location, on_behalf_of=principal) is False


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("perm", sorted(ADMIN_ON_BEHALF))
def test_only_the_admin_acts_in_someone_elses_name(perm, role, location):
    actor = make_account("gestora")
    make_member(actor, location, role)
    principal = make_account("pessoa")
    make_member(principal, location, PROFESSIONAL)

    assert has_perm_in(actor, perm, location, on_behalf_of=principal) is False
    assert not locations_with_perm(actor, perm, on_behalf_of=principal).exists()


def test_permissions_the_admin_holds_directly_cannot_be_used_in_someones_name(location):
    admin = make_account("admin", is_superuser=True)
    principal = make_account("pessoa")
    make_member(principal, location, COORDINATION)

    assert has_perm_in(admin, "salas.approve", location, on_behalf_of=principal) is False
    assert not locations_with_perm(admin, "salas.approve", on_behalf_of=principal).exists()


def test_inactive_location_stops_acting_in_someones_name(location):
    admin = make_account("admin", is_superuser=True)
    principal = make_account("pessoa")
    make_member(principal, location, PROFESSIONAL)
    location.is_active = False
    location.save()

    assert has_perm_in(admin, "salas.submit_request", location, on_behalf_of=principal) is False


def test_secretariat_of_one_location_does_not_see_details_in_another(location, other_location):
    secretary = make_account("secretaria")
    make_member(secretary, location, SECRETARIAT)

    rows = Location.objects.all()
    visible = filter_by_perm(rows, secretary, "salas.view_all_bookings", location_field="pk")

    assert list(visible) == [location]
    assert has_perm_in(secretary, "salas.view_all_bookings", other_location) is False
