import datetime

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core.models import Membership, Mentorship, Role, Subrole
from core.tests.conftest import END, START

pytestmark = pytest.mark.django_db


@pytest.fixture
def mentor(make_user, make_professional, location):
    user = make_user("orientadora@example.test")
    make_professional(user, location)
    return user


@pytest.fixture
def mentee(make_user, make_professional, location):
    user = make_user("orientanda@example.test")
    make_professional(user, location, subrole=Subrole.INTERN)
    return user


def mentorship(mentor, mentee, location, start_date=START, end_date=END):
    return Mentorship(
        mentor=mentor, mentee=mentee, location=location, start_date=start_date, end_date=end_date
    )


def errors_of(instance):
    with pytest.raises(ValidationError) as error:
        instance.full_clean()
    return error.value.message_dict


def test_professional_can_mentor_an_intern_in_the_same_location(mentor, mentee, location):
    relation = mentorship(mentor, mentee, location)

    relation.full_clean()
    relation.save()

    assert Mentorship.objects.active_on(START).get() == relation


def test_person_cannot_mentor_themselves(mentee, location):
    relation = mentorship(mentee, mentee, location)

    errors_of(relation)
    with pytest.raises(IntegrityError), transaction.atomic():
        relation.save()


def test_mentor_needs_a_professional_membership(make_user, mentee, location):
    secretary = make_user("secretariado@example.test")
    Membership.objects.create(
        user=secretary, location=location, role=Role.SECRETARIAT, start_date=START
    )

    assert "mentor" in errors_of(mentorship(secretary, mentee, location))


def test_mentee_must_be_an_intern(make_user, make_professional, mentor, location):
    resident = make_user("residente@example.test")
    make_professional(resident, location)

    assert "mentee" in errors_of(mentorship(mentor, resident, location))


def test_memberships_in_another_location_do_not_count(mentor, mentee, other_location):
    errors = errors_of(mentorship(mentor, mentee, other_location))

    assert {"mentor", "mentee"} <= set(errors)


def test_memberships_outside_the_dates_do_not_count(mentor, mentee, location):
    after_the_memberships = END + datetime.timedelta(days=1)

    errors = errors_of(mentorship(mentor, mentee, location, after_the_memberships, None))

    assert {"mentor", "mentee"} <= set(errors)


def test_admin_cannot_be_a_mentor(admin_user, mentee, location):
    assert "mentor" in errors_of(mentorship(admin_user, mentee, location))


def test_end_date_cannot_be_before_start_date(mentor, mentee, location):
    inverted = mentorship(mentor, mentee, location, END, START)

    assert list(errors_of(inverted)) == ["end_date"]
    with pytest.raises(IntegrityError), transaction.atomic():
        inverted.save()


def test_same_pair_cannot_overlap_in_the_same_location(mentor, mentee, location):
    mentorship(mentor, mentee, location).save()
    overlapping = mentorship(mentor, mentee, location, END, END)

    errors_of(overlapping)
    with pytest.raises(IntegrityError), transaction.atomic():
        overlapping.save()


def test_intern_can_have_two_mentors(make_user, make_professional, mentor, mentee, location):
    second_mentor = make_user("segunda@example.test")
    make_professional(second_mentor, location)
    mentorship(mentor, mentee, location).save()

    mentorship(second_mentor, mentee, location).full_clean()
