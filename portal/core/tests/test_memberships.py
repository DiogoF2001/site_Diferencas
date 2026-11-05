import datetime
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from core.models import Membership, Role, Subrole
from core.tests.conftest import END, START

pytestmark = pytest.mark.django_db


def membership(user, location, **fields):
    defaults = {
        "role": Role.PROFESSIONAL,
        "subrole": Subrole.RESIDENT,
        "start_date": START,
        "end_date": END,
    }
    return Membership(user=user, location=location, **{**defaults, **fields})


def assert_rejected_by_database(instance):
    with pytest.raises(IntegrityError), transaction.atomic():
        instance.save()


def test_person_can_have_several_roles_in_the_same_location(make_user, location):
    user = make_user()
    membership(user, location).save()
    second = membership(user, location, role=Role.SECRETARIAT, subrole="")

    second.full_clean()
    second.save()

    assert user.memberships.count() == 2


def test_person_can_have_the_same_role_in_another_location(make_user, location, other_location):
    user = make_user()
    membership(user, location).save()
    second = membership(user, other_location)

    second.full_clean()
    second.save()


def test_same_role_in_same_location_cannot_overlap(make_user, location):
    user = make_user()
    membership(user, location).save()
    overlapping = membership(
        user, location, start_date=END, end_date=END + datetime.timedelta(days=30)
    )

    with pytest.raises(ValidationError):
        overlapping.full_clean()
    assert_rejected_by_database(overlapping)


def test_overlap_rule_treats_open_end_as_never_ending(make_user, location):
    user = make_user()
    membership(user, location, end_date=None).save()
    later = membership(user, location, start_date=datetime.date(2030, 1, 1), end_date=None)

    with pytest.raises(ValidationError):
        later.full_clean()
    assert_rejected_by_database(later)


def test_overlap_rule_ignores_the_subrole(make_user, location):
    user = make_user()
    membership(user, location).save()

    with pytest.raises(ValidationError):
        membership(user, location, subrole=Subrole.INTERN).full_clean()


def test_same_role_can_return_on_the_day_after_it_ended(make_user, location):
    user = make_user()
    membership(user, location).save()
    next_period = membership(
        user, location, start_date=END + datetime.timedelta(days=1), end_date=None
    )

    next_period.full_clean()
    next_period.save()


def test_editing_a_membership_does_not_conflict_with_itself(make_user, location):
    existing = membership(make_user(), location)
    existing.save()

    existing.end_date = END + datetime.timedelta(days=1)

    existing.full_clean()


def test_end_date_cannot_be_before_start_date(make_user, location):
    inverted = membership(make_user(), location, end_date=START - datetime.timedelta(days=1))

    with pytest.raises(ValidationError) as error:
        inverted.full_clean()

    assert list(error.value.message_dict) == ["end_date"]
    assert_rejected_by_database(inverted)


def test_end_date_can_be_the_start_date(make_user, location):
    membership(make_user(), location, end_date=START).full_clean()


@pytest.mark.parametrize("subrole", [Subrole.RESIDENT, Subrole.INTERN])
def test_professional_accepts_either_subrole(make_user, location, subrole):
    membership(make_user(), location, subrole=subrole).full_clean()


def test_professional_needs_a_subrole(make_user, location):
    missing = membership(make_user(), location, subrole="")

    with pytest.raises(ValidationError):
        missing.full_clean()
    assert_rejected_by_database(missing)


@pytest.mark.parametrize("role", [Role.SECRETARIAT, Role.COORDINATION])
def test_other_roles_accept_no_subrole(make_user, location, role):
    membership(make_user(), location, role=role, subrole="", end_date=None).full_clean()


@pytest.mark.parametrize("role", [Role.SECRETARIAT, Role.COORDINATION])
def test_other_roles_cannot_have_a_subrole(make_user, location, role):
    wrong = membership(make_user(), location, role=role, subrole=Subrole.RESIDENT)

    with pytest.raises(ValidationError):
        wrong.full_clean()
    assert_rejected_by_database(wrong)


def test_intern_needs_an_end_date(make_user, location):
    open_ended = membership(make_user(), location, subrole=Subrole.INTERN, end_date=None)

    with pytest.raises(ValidationError):
        open_ended.full_clean()
    assert_rejected_by_database(open_ended)


def test_resident_can_be_open_ended(make_user, location):
    membership(make_user(), location, end_date=None).full_clean()


def test_admin_cannot_have_memberships(admin_user, location):
    with pytest.raises(ValidationError) as error:
        membership(admin_user, location).full_clean()

    assert "user" in error.value.message_dict


def test_user_and_location_with_memberships_cannot_be_deleted(make_user, location):
    user = make_user()
    membership(user, location).save()

    with pytest.raises(ProtectedError):
        user.delete()
    with pytest.raises(ProtectedError):
        location.delete()


@pytest.mark.parametrize(
    ("day", "active"),
    [
        (START - datetime.timedelta(days=1), False),
        (START, True),
        (END, True),
        (END + datetime.timedelta(days=1), False),
    ],
)
def test_active_on_includes_both_the_first_and_the_last_day(make_user, location, day, active):
    membership(make_user(), location).save()

    assert Membership.objects.active_on(day).exists() is active


def test_active_on_treats_no_end_date_as_never_ending(make_user, location):
    membership(make_user(), location, end_date=None).save()

    assert Membership.objects.active_on(datetime.date(2099, 1, 1)).exists()


def test_active_on_defaults_to_today_in_lisbon(make_user, location):
    membership(make_user(), location).save()

    with mock.patch("django.utils.timezone.localdate", return_value=END):
        assert Membership.objects.active_on().exists()
    with mock.patch(
        "django.utils.timezone.localdate", return_value=END + datetime.timedelta(days=1)
    ):
        assert not Membership.objects.active_on().exists()
