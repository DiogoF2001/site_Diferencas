"""Coordination's view of the account audit (core.view_audit, roadmap task 4b)."""

import pytest
from django.urls import reverse

from core.audit import Action, events_in, record
from core.models import Role
from core.tests.helpers import login_verified, make_account, make_member

pytestmark = pytest.mark.django_db


def staff(location, role, name):
    user = make_account(name)
    make_member(user, location, role)
    return user


def audit_page(client, location, **params):
    return client.get(reverse("audit_list", args=[location.pk]), params)


@pytest.fixture
def coordination(client, location):
    user = staff(location, Role.COORDINATION, "coordenacao")
    login_verified(client, user)
    return user


@pytest.fixture
def member(location):
    return staff(location, Role.PROFESSIONAL, "membro")


# Who sees it


def test_coordination_sees_the_audit_of_its_location(client, location, coordination, member):
    record(Action.MEMBERSHIP_CREATED, actor=coordination, target=member, location=location)

    response = audit_page(client, location)

    assert response.status_code == 200
    assert list(response.context["page"]) == list(events_in(location))
    assert "Filiação criada" in response.content.decode()


def test_secretariat_does_not_see_the_audit(client, location):
    login_verified(client, staff(location, Role.SECRETARIAT, "secretariado"))

    assert audit_page(client, location).status_code == 403


def test_professional_does_not_see_the_audit(client, location, member):
    login_verified(client, member)

    assert audit_page(client, location).status_code == 403


def test_coordination_of_location_a_does_not_see_location_b(
    client, location, other_location, coordination
):
    assert audit_page(client, other_location).status_code == 403


def test_admin_sees_the_audit_of_any_location(client, admin_user, other_location):
    login_verified(client, admin_user)

    assert audit_page(client, other_location).status_code == 200


def test_the_link_shows_only_for_coordination(client, location, coordination):
    home = client.get(reverse("home")).content.decode()
    members = client.get(reverse("member_list", args=[location.pk])).content.decode()

    assert reverse("audit_list", args=[location.pk]) in home
    assert reverse("audit_list", args=[location.pk]) in members


def test_secretariat_gets_no_link(client, location):
    login_verified(client, staff(location, Role.SECRETARIAT, "secretariado"))

    page = client.get(reverse("member_list", args=[location.pk])).content.decode()

    assert reverse("audit_list", args=[location.pk]) not in page
    assert reverse("mentorship_list", args=[location.pk]) in page


# What it shows


def test_events_of_other_locations_stay_out(location, other_location, member):
    make_member(member, other_location, Role.PROFESSIONAL)
    here = record(Action.MEMBERSHIP_CREATED, target=member, location=location)
    elsewhere = record(Action.MEMBERSHIP_CREATED, target=member, location=other_location)

    events = set(events_in(location))

    assert here in events
    assert elsewhere not in events


def test_account_events_of_members_are_shown(location, member):
    failed = record(Action.LOGIN_FAILED, target=member, email=member.email)
    deactivated = record(Action.ACCOUNT_DEACTIVATED, target=member)

    assert {failed, deactivated} <= set(events_in(location))


def test_account_events_of_people_elsewhere_stay_out(location, other_location):
    outsider = staff(other_location, Role.PROFESSIONAL, "de-fora")
    record(Action.LOGIN_FAILED, target=outsider, email=outsider.email)
    record(Action.PASSWORD_SET, target=outsider)

    assert not events_in(location).exists()


def test_account_events_of_former_members_stay_out(location):
    former = make_account("antiga")
    make_member(former, location, Role.PROFESSIONAL, start=-60, end=-1)
    record(Action.LOGIN_FAILED, target=former, email=former.email)

    assert not events_in(location).exists()


def test_future_members_count(location):
    future = make_account("futura")
    make_member(future, location, Role.PROFESSIONAL, start=5)
    event = record(Action.INVITATION_SENT, target=future)

    assert list(events_in(location)) == [event]


def test_failed_logins_for_unknown_addresses_stay_out(location):
    record(Action.LOGIN_FAILED, email="ninguem@example.test")

    assert not events_in(location).exists()


def test_filter_by_person_and_action(client, location, coordination, member):
    other = staff(location, Role.PROFESSIONAL, "outro")
    wanted = record(Action.MEMBERSHIP_CHANGED, target=member, location=location)
    record(Action.MEMBERSHIP_CREATED, target=member, location=location)
    record(Action.MEMBERSHIP_CHANGED, target=other, location=location)

    response = audit_page(client, location, person=member.pk, action=Action.MEMBERSHIP_CHANGED)

    assert list(response.context["page"]) == [wanted]


def test_filter_cannot_pick_someone_from_another_location(
    client, location, other_location, coordination
):
    outsider = staff(other_location, Role.PROFESSIONAL, "de-fora")
    record(Action.MEMBERSHIP_CREATED, target=outsider, location=other_location)

    response = audit_page(client, location, person=outsider.pk)

    assert response.context["form"].errors
    assert "de-fora" not in response.content.decode()


def test_changes_are_shown_in_words(client, location, coordination, member):
    record(
        Action.MEMBERSHIP_CHANGED,
        target=member,
        location=location,
        before={
            "role": "professional",
            "subrole": "intern",
            "start_date": "2026-01-01",
            "end_date": "2026-06-30",
        },
        after={"role": "secretariat", "subrole": "", "start_date": "2026-01-01", "end_date": None},
    )

    page = audit_page(client, location).content.decode()

    assert "Profissional (Estagiária), 01/01/2026 – 30/06/2026" in page
    assert "Secretariado, 01/01/2026 – …" in page


def test_pages_hold_fifty_events(client, location, coordination, member):
    for _event in range(55):
        record(Action.LOGIN_FAILED, target=member, email=member.email)

    first = audit_page(client, location)
    second = audit_page(client, location, pagina=2)

    assert len(first.context["page"]) == 50
    assert len(second.context["page"]) == 5
