"""Changing the role or the dates of a membership in the portal (roadmap, task 4b)."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory
from django.urls import reverse

from core import accounts
from core.models import AuditEvent, Membership, Role, Subrole
from core.tests.helpers import days_from_today, login_verified, make_account, make_member, today
from core.tests.test_two_factor import with_password

pytestmark = pytest.mark.django_db

Action = AuditEvent.Action


def staff(location, role, name=None):
    user = make_account(name or f"{role}-{location.pk}")
    make_member(user, location, role)
    return user


def edit_url(membership):
    return reverse("membership_edit", args=[membership.location_id, membership.pk])


def data(membership, **overrides):
    return {
        "role": membership.role,
        "subrole": membership.subrole,
        "start_date": membership.start_date.isoformat(),
        "end_date": membership.end_date.isoformat() if membership.end_date else "",
        **overrides,
    }


def change(membership, actor, **fields):
    values = {
        "role": membership.role,
        "subrole": membership.subrole,
        "start": membership.start_date,
        "end": membership.end_date,
        **fields,
    }
    request = RequestFactory().get("/", HTTP_HOST="testserver")
    return accounts.change_membership(request, actor, membership, **values)


@pytest.fixture
def secretariat(location):
    return staff(location, Role.SECRETARIAT)


@pytest.fixture
def as_secretariat(client, secretariat):
    login_verified(client, secretariat)
    return client


@pytest.fixture
def person(location):
    return make_account("pessoa")


# Who can change what


def test_secretariat_changes_the_end_date_of_a_professional(as_secretariat, location, person):
    membership = make_member(person, location, Role.PROFESSIONAL)
    new_end = days_from_today(90)

    response = as_secretariat.post(
        edit_url(membership), data(membership, end_date=new_end.isoformat())
    )

    assert response.status_code == 302
    membership.refresh_from_db()
    assert membership.end_date == new_end
    event = AuditEvent.objects.get(action=Action.MEMBERSHIP_CHANGED)
    assert event.target == person
    assert event.location == location
    assert event.details["before"]["end_date"] == days_from_today(30).isoformat()
    assert event.details["after"]["end_date"] == new_end.isoformat()


def test_secretariat_cannot_change_a_coordination_membership(as_secretariat, location, person):
    membership = make_member(person, location, Role.COORDINATION)

    response = as_secretariat.post(edit_url(membership), data(membership, end_date=""))

    assert response.status_code == 403
    membership.refresh_from_db()
    assert membership.end_date == days_from_today(30)


def test_secretariat_cannot_raise_a_role_to_coordination(as_secretariat, location, person):
    membership = make_member(person, location, Role.PROFESSIONAL, start=1)

    response = as_secretariat.post(
        edit_url(membership), data(membership, role=Role.COORDINATION, subrole="")
    )

    assert response.status_code == 200
    membership.refresh_from_db()
    assert membership.role == Role.PROFESSIONAL


def test_the_ceiling_holds_without_the_form(secretariat, location, person):
    membership = make_member(person, location, Role.PROFESSIONAL, start=1)

    with pytest.raises(PermissionDenied):
        change(membership, secretariat, role=Role.COORDINATION, subrole="")
    coordination = make_member(make_account("outra"), location, Role.COORDINATION)
    with pytest.raises(PermissionDenied):
        change(coordination, secretariat, end=days_from_today(1))


def test_secretariat_cannot_lower_a_coordination_role(secretariat, location, person):
    membership = make_member(person, location, Role.COORDINATION, start=1)

    with pytest.raises(PermissionDenied):
        change(membership, secretariat, role=Role.PROFESSIONAL, subrole=Subrole.RESIDENT)
    membership.refresh_from_db()
    assert membership.role == Role.COORDINATION


def test_coordination_can_give_coordination(client, location, person):
    login_verified(client, staff(location, Role.COORDINATION))
    membership = make_member(person, location, Role.PROFESSIONAL, start=1)

    client.post(edit_url(membership), data(membership, role=Role.COORDINATION, subrole=""))

    membership.refresh_from_db()
    assert membership.role == Role.COORDINATION
    assert membership.subrole == ""


def test_secretariat_of_location_a_cannot_change_memberships_in_b(
    as_secretariat, other_location, person
):
    membership = make_member(person, other_location, Role.PROFESSIONAL)

    response = as_secretariat.get(edit_url(membership))

    assert response.status_code == 403


def test_a_membership_of_another_location_is_not_found_through_this_one(
    as_secretariat, location, other_location, person
):
    make_member(person, location, Role.PROFESSIONAL)
    elsewhere = make_member(person, other_location, Role.PROFESSIONAL)

    url = reverse("membership_edit", args=[location.pk, elsewhere.pk])

    assert as_secretariat.get(url).status_code == 404


def test_professional_cannot_change_memberships(client, location, person):
    professional = staff(location, Role.PROFESSIONAL, "profissional")
    login_verified(client, professional)
    membership = make_member(person, location, Role.PROFESSIONAL)

    assert client.get(edit_url(membership)).status_code == 403
    with pytest.raises(PermissionDenied):
        change(membership, professional, end=days_from_today(1))


def test_an_ended_membership_cannot_be_changed(as_secretariat, secretariat, location, person):
    membership = make_member(person, location, Role.PROFESSIONAL, start=-30, end=-1)

    assert as_secretariat.get(edit_url(membership)).status_code == 404
    with pytest.raises(PermissionDenied):
        change(membership, secretariat, end=days_from_today(10))


def test_the_members_page_links_only_what_the_actor_may_change(as_secretariat, location, person):
    professional = make_member(person, location, Role.PROFESSIONAL)
    coordination = make_member(make_account("chefe"), location, Role.COORDINATION)

    page = as_secretariat.get(reverse("member_list", args=[location.pk])).content.decode()

    assert edit_url(professional) in page
    assert edit_url(coordination) not in page


# Dates


def test_a_start_date_that_has_passed_stays(secretariat, location, person):
    membership = make_member(person, location, Role.PROFESSIONAL)

    with pytest.raises(ValidationError) as error:
        change(membership, secretariat, start=days_from_today(-60))

    assert "start_date" in error.value.error_dict


def test_the_form_keeps_a_start_date_that_has_passed(as_secretariat, location, person):
    membership = make_member(person, location, Role.PROFESSIONAL)

    as_secretariat.post(
        edit_url(membership), data(membership, start_date=days_from_today(-60).isoformat())
    )

    membership.refresh_from_db()
    assert membership.start_date == days_from_today(-30)


def test_a_future_start_can_move_but_not_into_the_past(secretariat, location, person):
    membership = make_member(person, location, Role.PROFESSIONAL, start=5)

    change(membership, secretariat, start=days_from_today(2))
    membership.refresh_from_db()
    assert membership.start_date == days_from_today(2)
    with pytest.raises(ValidationError):
        change(membership, secretariat, start=days_from_today(-1))


def test_an_end_date_before_yesterday_is_refused(secretariat, location, person):
    membership = make_member(person, location, Role.PROFESSIONAL)

    with pytest.raises(ValidationError):
        change(membership, secretariat, end=days_from_today(-2))
    change(membership, secretariat, end=days_from_today(-1))
    membership.refresh_from_db()
    assert membership.end_date == days_from_today(-1)


def test_an_intern_keeps_needing_an_end_date(as_secretariat, location, person):
    membership = make_member(person, location, Role.PROFESSIONAL, subrole=Subrole.INTERN)

    response = as_secretariat.post(edit_url(membership), data(membership, end_date=""))

    assert response.status_code == 200
    membership.refresh_from_db()
    assert membership.end_date == days_from_today(30)


def test_saving_without_changes_records_nothing(secretariat, location, person):
    membership = make_member(person, location, Role.PROFESSIONAL)

    change(membership, secretariat)

    assert not AuditEvent.objects.filter(action=Action.MEMBERSHIP_CHANGED).exists()


# A new role does not rewrite the past


def test_a_new_role_after_the_start_ends_the_old_one_yesterday(secretariat, location, person):
    membership = make_member(person, location, Role.PROFESSIONAL, subrole=Subrole.INTERN)

    new, _sent = change(membership, secretariat, subrole=Subrole.RESIDENT, end=None)

    membership.refresh_from_db()
    assert membership.subrole == Subrole.INTERN
    assert membership.end_date == days_from_today(-1)
    assert new.pk != membership.pk
    assert (new.role, new.subrole) == (Role.PROFESSIONAL, Subrole.RESIDENT)
    assert new.start_date == today()
    assert new.end_date is None
    ended = AuditEvent.objects.get(action=Action.MEMBERSHIP_ENDED)
    created = AuditEvent.objects.get(action=Action.MEMBERSHIP_CREATED)
    assert ended.details["before"]["subrole"] == Subrole.INTERN
    assert ended.details["role_change"] is True
    assert created.details["after"]["subrole"] == Subrole.RESIDENT


def test_a_new_role_on_a_future_membership_changes_it_in_place(secretariat, location, person):
    membership = make_member(person, location, Role.PROFESSIONAL, start=3)

    new, _sent = change(membership, secretariat, role=Role.SECRETARIAT, subrole="")

    assert new.pk == membership.pk
    assert Membership.objects.filter(user=person).count() == 1
    assert AuditEvent.objects.filter(action=Action.MEMBERSHIP_CHANGED).count() == 1


def test_a_failed_role_change_leaves_the_old_membership_as_it_was(secretariat, location, person):
    membership = make_member(person, location, Role.PROFESSIONAL)
    make_member(person, location, Role.SECRETARIAT, start=-5, end=None)

    with pytest.raises(ValidationError):
        change(membership, secretariat, role=Role.SECRETARIAT, subrole="")

    membership.refresh_from_db()
    assert membership.end_date == days_from_today(30)
    assert not AuditEvent.objects.exists()


# 2FA, as when the role is first given


def test_a_staff_role_sends_the_2fa_link(as_secretariat, location, person, mailoutbox):
    with_password(person)
    membership = make_member(person, location, Role.PROFESSIONAL, start=2)

    response = as_secretariat.post(
        edit_url(membership), data(membership, role=Role.SECRETARIAT, subrole=""), follow=True
    )

    assert len(mailoutbox) == 1
    assert "/conta/2fa/link/" in mailoutbox[0].body
    assert AuditEvent.objects.filter(action=Action.TWO_FACTOR_LINK_SENT, target=person).exists()
    assert "o link para a configurar foi enviado" in response.content.decode()


def test_changing_only_the_dates_of_a_staff_role_sends_nothing(
    secretariat, location, person, mailoutbox
):
    with_password(person)
    membership = make_member(person, location, Role.SECRETARIAT, start=2)

    change(membership, secretariat, end=days_from_today(100))

    assert mailoutbox == []


def test_a_failed_2fa_link_keeps_the_new_role(as_secretariat, location, person, monkeypatch):
    with_password(person)
    membership = make_member(person, location, Role.PROFESSIONAL, start=2)

    def fail(*args, **kwargs):
        raise OSError("smtp down")

    monkeypatch.setattr("core.accounts.send_mail", fail)
    response = as_secretariat.post(
        edit_url(membership), data(membership, role=Role.SECRETARIAT, subrole=""), follow=True
    )

    membership.refresh_from_db()
    assert membership.role == Role.SECRETARIAT
    assert AuditEvent.objects.filter(action=Action.TWO_FACTOR_LINK_FAILED).exists()
    assert "Não foi possível enviar o link do 2FA" in response.content.decode()
