"""The mentorships screen (core.manage_mentorships, roadmap task 4b)."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from core import mentorships
from core.models import AuditEvent, Mentorship, Role, Subrole
from core.permissions import mentees_of
from core.tests.helpers import (
    days_from_today,
    login_verified,
    make_account,
    make_member,
    make_mentorship,
    today,
)

pytestmark = pytest.mark.django_db

Action = AuditEvent.Action


def staff(location, role, name):
    user = make_account(name)
    make_member(user, location, role)
    return user


@pytest.fixture
def mentor(location):
    return staff(location, Role.PROFESSIONAL, "orientadora")


@pytest.fixture
def mentee(location):
    user = make_account("estagiaria")
    make_member(user, location, Role.PROFESSIONAL, subrole=Subrole.INTERN)
    return user


def form_data(mentor, mentee, **overrides):
    return {
        "mentor": mentor.pk,
        "mentee": mentee.pk,
        "start_date": today().isoformat(),
        "end_date": days_from_today(30).isoformat(),
        **overrides,
    }


# Who can open and use the screen


@pytest.mark.parametrize("role", [Role.SECRETARIAT, Role.COORDINATION])
def test_staff_add_a_mentorship(client, location, mentor, mentee, role):
    actor = staff(location, role, "staff")
    login_verified(client, actor)

    response = client.post(reverse("mentorship_add", args=[location.pk]), form_data(mentor, mentee))

    assert response.status_code == 302
    mentorship = Mentorship.objects.get()
    assert (mentorship.mentor, mentorship.mentee, mentorship.location) == (
        mentor,
        mentee,
        location,
    )
    assert mentees_of(mentor, location).filter(pk=mentee.pk).exists()
    event = AuditEvent.objects.get(action=Action.MENTORSHIP_CREATED)
    assert (event.actor, event.target, event.location) == (actor, mentee, location)
    assert event.details["after"]["mentor"] == mentor.email


def test_professional_cannot_open_or_use_the_screen(client, location, mentor, mentee):
    login_verified(client, mentor)

    assert client.get(reverse("mentorship_list", args=[location.pk])).status_code == 403
    response = client.post(reverse("mentorship_add", args=[location.pk]), form_data(mentor, mentee))
    assert response.status_code == 403
    with pytest.raises(PermissionDenied):
        mentorships.create_mentorship(
            mentor, location, mentor=mentor, mentee=mentee, start=today(), end=None
        )
    assert not Mentorship.objects.exists()


def test_secretariat_of_location_a_cannot_manage_mentorships_in_b(
    client, location, other_location, mentor, mentee
):
    actor = staff(other_location, Role.SECRETARIAT, "secretariado-b")
    login_verified(client, actor)
    mentorship = make_mentorship(mentor, mentee, location)

    assert client.get(reverse("mentorship_list", args=[location.pk])).status_code == 403
    url = reverse("mentorship_end", args=[location.pk, mentorship.pk])
    assert client.post(url).status_code == 403
    with pytest.raises(PermissionDenied):
        mentorships.end_mentorship(actor, mentorship)


def test_a_mentorship_of_another_location_is_not_found_through_this_one(
    client, location, other_location, mentor, mentee
):
    login_verified(client, staff(location, Role.SECRETARIAT, "secretariado"))
    make_member(mentor, other_location, Role.PROFESSIONAL)
    make_member(mentee, other_location, Role.PROFESSIONAL, subrole=Subrole.INTERN)
    elsewhere = make_mentorship(mentor, mentee, other_location)

    response = client.post(reverse("mentorship_end", args=[location.pk, elsewhere.pk]))

    assert response.status_code == 404
    elsewhere.refresh_from_db()
    assert elsewhere.end_date == days_from_today(30)


def test_the_list_shows_only_this_location(client, location, other_location, mentor, mentee):
    login_verified(client, staff(location, Role.SECRETARIAT, "secretariado"))
    other_mentor = staff(other_location, Role.PROFESSIONAL, "orientadora-b")
    other_mentee = make_account("estagiaria-b")
    make_member(other_mentee, other_location, Role.PROFESSIONAL, subrole=Subrole.INTERN)
    make_mentorship(mentor, mentee, location)
    make_mentorship(other_mentor, other_mentee, other_location)

    page = client.get(reverse("mentorship_list", args=[location.pk])).content.decode()

    assert "orientadora" in page
    assert "orientadora-b" not in page


def test_the_form_offers_only_this_location_professionals_and_interns(
    client, location, other_location, mentor, mentee
):
    login_verified(client, staff(location, Role.SECRETARIAT, "secretariado"))
    outsider = staff(other_location, Role.PROFESSIONAL, "de-fora")

    response = client.post(
        reverse("mentorship_add", args=[location.pk]), form_data(outsider, mentee)
    )
    assert response.status_code == 200
    response = client.post(reverse("mentorship_add", args=[location.pk]), form_data(mentee, mentor))
    assert response.status_code == 200
    assert not Mentorship.objects.exists()


def test_the_dates_must_fit_the_memberships(client, location, mentor, mentee):
    login_verified(client, staff(location, Role.SECRETARIAT, "secretariado"))

    response = client.post(
        reverse("mentorship_add", args=[location.pk]),
        form_data(
            mentor,
            mentee,
            start_date=days_from_today(60).isoformat(),
            end_date=days_from_today(90).isoformat(),
        ),
    )

    assert response.status_code == 200
    assert set(response.context["form"].errors) == {"mentor", "mentee"}
    assert not Mentorship.objects.exists()


# Changing and ending


def test_change_the_end_date(client, location, mentor, mentee):
    login_verified(client, staff(location, Role.COORDINATION, "coordenacao"))
    mentorship = make_mentorship(mentor, mentee, location, end=10)

    client.post(
        reverse("mentorship_edit", args=[location.pk, mentorship.pk]),
        {"start_date": mentorship.start_date.isoformat(), "end_date": days_from_today(20)},
    )

    mentorship.refresh_from_db()
    assert mentorship.end_date == days_from_today(20)
    event = AuditEvent.objects.get(action=Action.MENTORSHIP_CHANGED)
    assert event.details["before"]["end_date"] == days_from_today(10).isoformat()


def test_a_start_date_that_has_passed_stays(location, mentor, mentee):
    actor = staff(location, Role.SECRETARIAT, "secretariado")
    mentorship = make_mentorship(mentor, mentee, location, start=-10)

    with pytest.raises(ValidationError):
        mentorships.change_mentorship(
            actor, mentorship, start=days_from_today(-20), end=mentorship.end_date
        )


def test_ending_an_active_mentorship_ends_it_yesterday(client, location, mentor, mentee):
    login_verified(client, staff(location, Role.SECRETARIAT, "secretariado"))
    mentorship = make_mentorship(mentor, mentee, location)

    client.post(reverse("mentorship_end", args=[location.pk, mentorship.pk]))

    mentorship.refresh_from_db()
    assert mentorship.end_date == days_from_today(-1)
    assert not mentees_of(mentor, location).exists()
    assert AuditEvent.objects.filter(action=Action.MENTORSHIP_ENDED, target=mentee).exists()


def test_ending_a_future_mentorship_deletes_it(location, mentor, mentee):
    actor = staff(location, Role.SECRETARIAT, "secretariado")
    mentorship = make_mentorship(mentor, mentee, location, start=2)

    mentorships.end_mentorship(actor, mentorship)

    assert not Mentorship.objects.exists()
    event = AuditEvent.objects.get(action=Action.MENTORSHIP_DELETED)
    assert event.details["before"]["start_date"] == days_from_today(2).isoformat()


def test_an_ended_mentorship_cannot_be_changed(location, mentor, mentee):
    actor = staff(location, Role.SECRETARIAT, "secretariado")
    mentorship = make_mentorship(mentor, mentee, location, start=-20, end=-2)

    with pytest.raises(PermissionDenied):
        mentorships.end_mentorship(actor, mentorship)
    with pytest.raises(PermissionDenied):
        mentorships.change_mentorship(actor, mentorship, start=mentorship.start_date, end=None)
