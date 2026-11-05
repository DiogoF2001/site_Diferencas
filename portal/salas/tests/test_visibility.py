import pytest

from core.models import Location, Role, Subrole
from core.tests.helpers import make_account, make_member, make_mentorship
from salas.permissions import people_with_visible_hours, people_with_visible_schedule

pytestmark = pytest.mark.django_db

BOTH = [people_with_visible_schedule, people_with_visible_hours]


@pytest.fixture
def polo_a():
    return Location.objects.create(name="Polo A")


@pytest.fixture
def polo_b():
    return Location.objects.create(name="Polo B")


def member(name, location, role=Role.PROFESSIONAL, **fields):
    user = make_account(name)
    make_member(user, location, role, **fields)
    return user


@pytest.mark.parametrize("visible_people", BOTH)
def test_professional_sees_only_themselves(visible_people, polo_a):
    user = member("pessoa", polo_a)
    member("colega", polo_a)

    assert list(visible_people(user, polo_a)) == [user]


@pytest.mark.parametrize("visible_people", BOTH)
def test_mentor_also_sees_the_mentee_in_that_location(visible_people, polo_a):
    mentor = member("orientadora", polo_a)
    mentee = member("orientanda", polo_a, subrole=Subrole.INTERN)
    other = member("colega", polo_a)
    make_mentorship(mentor, mentee, polo_a)

    visible = visible_people(mentor, polo_a)

    assert set(visible) == {mentor, mentee}
    assert other not in visible


@pytest.mark.parametrize("visible_people", BOTH)
def test_mentee_does_not_see_the_mentor(visible_people, polo_a):
    mentor = member("orientadora", polo_a)
    mentee = member("orientanda", polo_a, subrole=Subrole.INTERN)
    make_mentorship(mentor, mentee, polo_a)

    assert list(visible_people(mentee, polo_a)) == [mentee]


@pytest.mark.parametrize("visible_people", BOTH)
def test_mentor_does_not_see_the_mentee_in_another_location(visible_people, polo_a, polo_b):
    mentor = member("orientadora", polo_a)
    mentee = member("orientanda", polo_a, subrole=Subrole.INTERN)
    make_mentorship(mentor, mentee, polo_a)
    make_member(mentor, polo_b, Role.PROFESSIONAL)
    make_member(mentee, polo_b, Role.PROFESSIONAL, subrole=Subrole.INTERN)

    assert list(visible_people(mentor, polo_b)) == [mentor]


@pytest.mark.parametrize("visible_people", BOTH)
def test_mentor_stops_seeing_the_mentee_when_the_mentorship_ends(visible_people, polo_a):
    mentor = member("orientadora", polo_a)
    mentee = member("orientanda", polo_a, subrole=Subrole.INTERN)
    make_mentorship(mentor, mentee, polo_a, end=-1)

    assert list(visible_people(mentor, polo_a)) == [mentor]


@pytest.mark.parametrize("visible_people", BOTH)
@pytest.mark.parametrize(
    "start,end", [pytest.param(-30, -1, id="expired"), pytest.param(1, 30, id="not_started")]
)
def test_nothing_is_visible_without_an_active_membership(visible_people, start, end, polo_a):
    mentee = member("orientanda", polo_a, subrole=Subrole.INTERN)
    mentor = member("orientadora", polo_a, start=start, end=end)
    make_mentorship(mentor, mentee, polo_a)

    assert not visible_people(mentor, polo_a).exists()


@pytest.mark.parametrize("visible_people", BOTH)
def test_nothing_is_visible_in_another_location(visible_people, polo_a, polo_b):
    user = member("pessoa", polo_a, Role.COORDINATION)
    member("colega", polo_b)

    assert not visible_people(user, polo_b).exists()


def test_secretariat_sees_every_schedule_but_only_their_own_hours(polo_a):
    secretary = member("secretaria", polo_a, Role.SECRETARIAT)
    colleague = member("colega", polo_a)

    assert set(people_with_visible_schedule(secretary, polo_a)) == {secretary, colleague}
    assert list(people_with_visible_hours(secretary, polo_a)) == [secretary]


@pytest.mark.parametrize("visible_people", BOTH)
def test_coordination_sees_the_location_including_past_members(visible_people, polo_a, polo_b):
    coordinator = member("coordenadora", polo_a, Role.COORDINATION)
    past_intern = member("antiga", polo_a, subrole=Subrole.INTERN, start=-90, end=-30)
    elsewhere = member("fora", polo_b)

    visible = visible_people(coordinator, polo_a)

    assert set(visible) == {coordinator, past_intern}
    assert elsewhere not in visible


@pytest.mark.parametrize("visible_people", BOTH)
def test_person_with_two_roles_appears_once(visible_people, polo_a):
    coordinator = member("coordenadora", polo_a, Role.COORDINATION)
    make_member(coordinator, polo_a, Role.PROFESSIONAL)

    assert list(visible_people(coordinator, polo_a)) == [coordinator]


@pytest.mark.parametrize("visible_people", BOTH)
def test_admin_sees_the_members_of_any_location_but_is_not_one(visible_people, polo_a):
    admin = make_account("admin", is_superuser=True)
    user = member("pessoa", polo_a)

    assert list(visible_people(admin, polo_a)) == [user]
