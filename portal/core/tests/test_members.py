import datetime
import re
import smtplib

import pytest
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from core import accounts, permissions
from core.models import AuditEvent, Membership, Role, Subrole, User
from core.tests.helpers import (
    days_from_today,
    login_verified,
    make_account,
    make_member,
    today,
)

pytestmark = pytest.mark.django_db

Action = AuditEvent.Action
PASSWORD = "uma-palavra-passe-nova-e-longa"


def staff(location, role, name=None):
    user = make_account(name or f"{role}-{location.pk}")
    make_member(user, location, role)
    return user


@pytest.fixture
def secretariat(location):
    return staff(location, Role.SECRETARIAT)


@pytest.fixture
def coordination(location):
    return staff(location, Role.COORDINATION)


@pytest.fixture
def as_secretariat(client, secretariat):
    login_verified(client, secretariat)
    return client


def member_data(**overrides):
    return {
        "email": "Nova@example.test",
        "full_name": "Nova Pessoa",
        "role": Role.PROFESSIONAL,
        "subrole": Subrole.RESIDENT,
        "start_date": today().isoformat(),
        "end_date": "",
        **overrides,
    }


def add(client, location, **overrides):
    return client.post(reverse("member_add", args=[location.pk]), member_data(**overrides))


def link_in(message):
    return re.search(r"https?://\S+/conta/definir/\S+/", message.body).group(0)


# Who sees the members page


def test_secretariat_sees_the_members_of_its_location(as_secretariat, location):
    response = as_secretariat.get(reverse("member_list", args=[location.pk]))

    assert response.status_code == 200


def test_secretariat_of_location_a_cannot_open_location_b(as_secretariat, other_location):
    staff(other_location, Role.PROFESSIONAL)

    response = as_secretariat.get(reverse("member_list", args=[other_location.pk]))

    assert response.status_code == 403


def test_professional_cannot_open_the_members_page(client, location):
    person = staff(location, Role.PROFESSIONAL)
    client.force_login(person)

    assert client.get(reverse("member_list", args=[location.pk])).status_code == 403
    assert add(client, location).status_code == 403


def test_anonymous_is_sent_to_login(client, location):
    response = client.get(reverse("member_list", args=[location.pk]))

    assert response.url.startswith(reverse("login"))


def test_members_page_shows_no_roles_from_other_locations(as_secretariat, location, other_location):
    person = staff(location, Role.PROFESSIONAL, "partilhada")
    make_member(person, other_location, Role.COORDINATION)

    page = as_secretariat.get(reverse("member_list", args=[location.pk])).content.decode()

    assert "partilhada" in page
    assert "Coordenação" not in page.split("<tbody>")[1].split("partilhada")[1]
    assert "Polo B" not in page


# Adding members


def test_new_email_creates_an_account_and_sends_a_one_time_invitation(
    as_secretariat, location, mailoutbox, secretariat
):
    response = add(as_secretariat, location)

    assert response.status_code == 302
    person = User.objects.get(email="nova@example.test")
    assert not person.has_usable_password()
    membership = person.memberships.get()
    assert (membership.location, membership.role) == (location, Role.PROFESSIONAL)
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["nova@example.test"]
    assert "Convite" in mailoutbox[0].subject
    actions = set(AuditEvent.objects.filter(target=person).values_list("action", "actor"))
    assert actions == {
        (Action.MEMBERSHIP_CREATED, secretariat.pk),
        (Action.INVITATION_SENT, secretariat.pk),
    }

    link = link_in(mailoutbox[0])
    invited = Client()
    form_page = invited.get(link, follow=True)
    set_url = form_page.redirect_chain[-1][0]
    response = invited.post(set_url, {"new_password1": PASSWORD, "new_password2": PASSWORD})

    assert response.url == reverse("login")
    person.refresh_from_db()
    assert person.check_password(PASSWORD)
    assert AuditEvent.objects.filter(action=Action.PASSWORD_SET, target=person).exists()
    # The link works only once.
    again = Client().get(link, follow=True).content.decode()
    assert "já não é válido" in again


def test_invitation_expires_after_48_hours(as_secretariat, location, mailoutbox, monkeypatch):
    add(as_secretariat, location)
    link = link_in(mailoutbox[0])
    later = datetime.datetime.now() + datetime.timedelta(hours=48, minutes=1)

    monkeypatch.setattr(
        "django.contrib.auth.tokens.PasswordResetTokenGenerator._now", lambda self: later
    )

    assert "já não é válido" in Client().get(link, follow=True).content.decode()
    assert settings.PASSWORD_RESET_TIMEOUT == 48 * 3600


def test_deactivating_the_account_invalidates_the_invitation(as_secretariat, location, mailoutbox):
    add(as_secretariat, location)
    User.objects.filter(email="nova@example.test").update(is_active=False)

    page = Client().get(link_in(mailoutbox[0]), follow=True).content.decode()

    assert "já não é válido" in page


def test_existing_email_only_gets_the_membership(
    as_secretariat, location, other_location, mailoutbox
):
    person = staff(other_location, Role.PROFESSIONAL, "existente")

    response = add(as_secretariat, location, email="EXISTENTE@example.test", full_name="")

    assert response.status_code == 302
    assert person.memberships.filter(location=location).exists()
    assert User.objects.filter(email="existente@example.test").count() == 1
    assert mailoutbox == []


def test_new_account_needs_a_name(as_secretariat, location):
    response = add(as_secretariat, location, full_name="")

    assert response.status_code == 200
    assert not User.objects.filter(email="nova@example.test").exists()


def test_intern_needs_an_end_date(as_secretariat, location):
    response = add(as_secretariat, location, subrole=Subrole.INTERN)

    assert response.status_code == 200
    assert "estagiária" in response.content.decode().lower()
    assert not User.objects.filter(email="nova@example.test").exists()


def test_admin_account_cannot_get_a_membership(as_secretariat, location, admin_user):
    response = add(as_secretariat, location, email=admin_user.email)

    assert response.status_code == 200
    assert not Membership.objects.filter(user=admin_user).exists()


@pytest.mark.parametrize(
    ("actor_role", "role", "allowed"),
    [
        (Role.SECRETARIAT, Role.PROFESSIONAL, True),
        (Role.SECRETARIAT, Role.SECRETARIAT, True),
        (Role.SECRETARIAT, Role.COORDINATION, False),
        (Role.COORDINATION, Role.COORDINATION, True),
    ],
)
def test_roles_only_up_to_the_actors_own_level(client, location, actor_role, role, allowed):
    login_verified(client, staff(location, actor_role))
    subrole = Subrole.RESIDENT if role == Role.PROFESSIONAL else ""
    response = add(client, location, role=role, subrole=subrole)

    assert User.objects.filter(email="nova@example.test").exists() is allowed
    if not allowed:
        assert response.status_code == 200


def test_secretariat_cannot_add_members_to_another_location(as_secretariat, other_location):
    response = add(as_secretariat, other_location)

    assert response.status_code == 403
    assert not User.objects.filter(email="nova@example.test").exists()


def test_failed_email_leaves_no_account(as_secretariat, location, monkeypatch):
    def fail(*args, **kwargs):
        raise smtplib.SMTPException("down")

    monkeypatch.setattr("core.accounts.send_mail", fail)

    response = add(as_secretariat, location)

    assert response.status_code == 200
    assert not User.objects.filter(email="nova@example.test").exists()
    assert not AuditEvent.objects.filter(action=Action.MEMBERSHIP_CREATED).exists()


# Removing from the location


def test_remove_ends_active_roles_yesterday_and_deletes_future_ones(
    as_secretariat, location, secretariat
):
    person = staff(location, Role.PROFESSIONAL, "sai")
    future = make_member(person, location, Role.SECRETARIAT, start=10, end=None)

    response = as_secretariat.post(reverse("member_remove", args=[location.pk, person.pk]))

    assert response.status_code == 302
    remaining = person.memberships.get()
    assert remaining.end_date == days_from_today(-1)
    assert not Membership.objects.filter(pk=future.pk).exists()
    actions = sorted(AuditEvent.objects.filter(target=person).values_list("action", flat=True))
    assert actions == [Action.MEMBERSHIP_DELETED, Action.MEMBERSHIP_ENDED]


def test_removed_person_loses_access_at_once(as_secretariat, location):
    person = staff(location, Role.PROFESSIONAL, "sai")
    their_client = Client()
    their_client.force_login(person)

    as_secretariat.post(reverse("member_remove", args=[location.pk, person.pk]))

    assert their_client.get(reverse("home")).url.startswith(reverse("login"))


def test_secretariat_cannot_remove_coordination(as_secretariat, location, coordination):
    response = as_secretariat.post(reverse("member_remove", args=[location.pk, coordination.pk]))

    assert response.status_code == 403
    assert coordination.memberships.get().end_date == days_from_today(30)


def test_cannot_remove_someone_through_another_location(as_secretariat, location, other_location):
    elsewhere = staff(other_location, Role.PROFESSIONAL, "fora")

    response = as_secretariat.post(reverse("member_remove", args=[location.pk, elsewhere.pk]))

    assert response.status_code == 404
    assert elsewhere.memberships.get().end_date == days_from_today(30)


def test_remove_needs_a_post(as_secretariat, location):
    person = staff(location, Role.PROFESSIONAL, "fica")

    response = as_secretariat.get(reverse("member_remove", args=[location.pk, person.pk]))

    assert response.status_code == 405


# Whole-account actions


def test_deactivate_and_reactivate_are_audited(as_secretariat, location, secretariat):
    person = staff(location, Role.PROFESSIONAL, "conta")

    as_secretariat.post(reverse("account_deactivate", args=[location.pk, person.pk]))
    person.refresh_from_db()
    assert not person.is_active

    as_secretariat.post(reverse("account_reactivate", args=[location.pk, person.pk]))
    person.refresh_from_db()
    assert person.is_active

    actions = list(
        AuditEvent.objects.filter(target=person).order_by("pk").values_list("action", "actor")
    )
    assert actions == [
        (Action.ACCOUNT_DEACTIVATED, secretariat.pk),
        (Action.ACCOUNT_REACTIVATED, secretariat.pk),
    ]


def test_cannot_deactivate_someone_with_a_higher_role_elsewhere(
    as_secretariat, location, other_location
):
    person = staff(location, Role.PROFESSIONAL, "dupla")
    make_member(person, other_location, Role.SECRETARIAT)

    response = as_secretariat.post(reverse("account_deactivate", args=[location.pk, person.pk]))

    assert response.status_code == 403
    person.refresh_from_db()
    assert person.is_active


def test_cannot_deactivate_own_account(as_secretariat, location, secretariat):
    response = as_secretariat.post(
        reverse("account_deactivate", args=[location.pk, secretariat.pk])
    )

    assert response.status_code == 403


def test_reset_two_factor(client, location, coordination):
    login_verified(client, coordination)
    person = staff(location, Role.SECRETARIAT, "perdeu")
    TOTPDevice.objects.create(user=person, name="default", confirmed=True)

    client.post(reverse("account_reset_two_factor", args=[location.pk, person.pk]))

    assert not TOTPDevice.objects.filter(user=person).exists()
    event = AuditEvent.objects.get(action=Action.TWO_FACTOR_RESET)
    assert (event.actor, event.target) == (coordination, person)


def test_secretariat_cannot_reset_coordinations_two_factor(as_secretariat, location, coordination):
    TOTPDevice.objects.create(user=coordination, name="default", confirmed=True)

    response = as_secretariat.post(
        reverse("account_reset_two_factor", args=[location.pk, coordination.pk])
    )

    assert response.status_code == 403
    assert TOTPDevice.objects.filter(user=coordination).exists()


# Recovery links


def test_recovery_link_is_sent_and_audited(as_secretariat, location, mailoutbox, secretariat):
    person = staff(location, Role.PROFESSIONAL, "esqueceu")
    person.set_password("a-antiga-palavra-passe")
    person.save()

    as_secretariat.post(reverse("account_send_link", args=[location.pk, person.pk]))

    assert len(mailoutbox) == 1
    assert "palavra-passe" in mailoutbox[0].subject
    event = AuditEvent.objects.get(action=Action.RECOVERY_LINK_SENT)
    assert (event.actor, event.target, event.location) == (secretariat, person, location)


def test_link_to_an_account_that_never_set_a_password_is_a_new_invitation(
    as_secretariat, location, mailoutbox
):
    person = staff(location, Role.PROFESSIONAL, "convidada")

    as_secretariat.post(reverse("account_send_link", args=[location.pk, person.pk]))

    assert "Convite" in mailoutbox[0].subject
    assert AuditEvent.objects.filter(action=Action.INVITATION_SENT, target=person).exists()


def test_recovery_links_have_an_hourly_limit(as_secretariat, location, mailoutbox):
    person = staff(location, Role.PROFESSIONAL, "muitos")

    for _attempt in range(settings.PORTAL_ACCOUNT_EMAILS_PER_HOUR + 1):
        as_secretariat.post(reverse("account_send_link", args=[location.pk, person.pk]))

    assert len(mailoutbox) == settings.PORTAL_ACCOUNT_EMAILS_PER_HOUR


def test_recovery_link_limit_resets_after_an_hour(as_secretariat, location, mailoutbox):
    person = staff(location, Role.PROFESSIONAL, "muitos")
    long_ago = timezone.now() - datetime.timedelta(hours=1, minutes=1)
    for _attempt in range(settings.PORTAL_ACCOUNT_EMAILS_PER_HOUR):
        AuditEvent.objects.create(
            action=Action.RECOVERY_LINK_SENT, target=person, created_at=long_ago
        )

    as_secretariat.post(reverse("account_send_link", args=[location.pk, person.pk]))

    assert len(mailoutbox) == 1


def test_secretariat_can_send_a_link_to_a_member_with_a_future_role(
    as_secretariat, location, mailoutbox
):
    person = make_account("futura")
    make_member(person, location, Role.PROFESSIONAL, start=7, end=None)

    as_secretariat.post(reverse("account_send_link", args=[location.pk, person.pk]))

    assert len(mailoutbox) == 1


def test_no_link_for_someone_who_is_not_in_the_location(
    as_secretariat, location, other_location, mailoutbox
):
    elsewhere = staff(other_location, Role.PROFESSIONAL, "fora")

    response = as_secretariat.post(reverse("account_send_link", args=[location.pk, elsewhere.pk]))

    assert response.status_code == 404
    assert mailoutbox == []


def test_professional_cannot_send_links(client, location, mailoutbox):
    person = staff(location, Role.PROFESSIONAL, "colega")
    actor = staff(location, Role.PROFESSIONAL, "outra")
    client.force_login(actor)

    response = client.post(reverse("account_send_link", args=[location.pk, person.pk]))

    assert response.status_code == 403
    assert mailoutbox == []


def test_no_link_to_a_deactivated_account(as_secretariat, location, mailoutbox):
    person = staff(location, Role.PROFESSIONAL, "inativa")
    person.is_active = False
    person.save()

    response = as_secretariat.post(reverse("account_send_link", args=[location.pk, person.pk]))

    assert response.status_code == 403
    assert mailoutbox == []


# Self-service recovery, prepared but off


def test_self_service_recovery_is_off_by_default(client):
    assert settings.PORTAL_SELF_PASSWORD_RESET is False
    assert client.get(reverse("password_reset")).status_code == 404
    assert "secretariado" in client.get(reverse("login")).content.decode()


def test_self_service_recovery_when_switched_on(client, settings, location, mailoutbox):
    settings.PORTAL_SELF_PASSWORD_RESET = True
    person = staff(location, Role.PROFESSIONAL, "propria")
    # Like Django, only accounts that already have a password; the others need an invitation.
    person.set_password("a-antiga-palavra-passe")
    person.save()

    known = client.post(reverse("password_reset"), {"email": person.email})
    unknown = client.post(reverse("password_reset"), {"email": "ninguem@example.test"})

    assert known.content == unknown.content
    assert len(mailoutbox) == 1
    event = AuditEvent.objects.get(target=person)
    assert event.actor is None


# Coordination's list


@pytest.fixture
def as_coordination(client, coordination):
    login_verified(client, coordination)
    return client


def test_coordination_lists_members_and_optionally_their_other_roles(
    as_coordination, location, other_location
):
    person = staff(location, Role.PROFESSIONAL, "listada")
    make_member(person, other_location, Role.SECRETARIAT)
    url = reverse("professional_list", args=[location.pk])

    plain = as_coordination.get(url).content.decode()
    detailed = as_coordination.get(url, {"outros": "1"}).content.decode()

    assert "listada" in plain
    assert "Polo B" not in plain
    assert "Polo B" in detailed


def test_list_leaves_out_people_who_have_left(as_coordination, location):
    staff(location, Role.PROFESSIONAL, "antiga")
    Membership.objects.filter(user__email="antiga@example.test").update(
        start_date=days_from_today(-60), end_date=days_from_today(-1)
    )

    page = as_coordination.get(reverse("professional_list", args=[location.pk]))

    assert "antiga" not in page.content.decode()


@pytest.mark.parametrize("role", [Role.SECRETARIAT, Role.PROFESSIONAL])
def test_only_coordination_opens_the_list(client, location, role):
    login_verified(client, staff(location, role))

    assert client.get(reverse("professional_list", args=[location.pk])).status_code == 403


def test_coordination_of_location_a_cannot_list_location_b(as_coordination, other_location):
    assert (
        as_coordination.get(reverse("professional_list", args=[other_location.pk])).status_code
        == 403
    )


def test_list_exports_csv_safe_for_spreadsheets(as_coordination, location, other_location):
    person = make_account("formula")
    person.full_name = "=HYPERLINK(1)"
    person.save()
    make_member(person, location, Role.PROFESSIONAL)
    make_member(person, other_location, Role.COORDINATION)

    response = as_coordination.get(
        reverse("professional_list", args=[location.pk]), {"outros": "1", "formato": "csv"}
    )

    assert response["Content-Type"].startswith("text/csv")
    assert "attachment" in response["Content-Disposition"]
    content = response.content.decode("utf-8")
    assert content.startswith("\ufeffNome;Endereço de e-mail;Conta;Papéis neste polo")
    assert "'=HYPERLINK(1)" in content
    assert "Polo B: Coordenação" in content


# The rules hold without the views' own checks


def test_add_member_refuses_a_role_above_the_actor_even_without_the_form(secretariat, location, rf):
    with pytest.raises(PermissionDenied):
        accounts.add_member(
            rf.get("/"),
            secretariat,
            location,
            email="nova@example.test",
            full_name="Nova",
            role=Role.COORDINATION,
            subrole="",
            start=today(),
            end=None,
        )

    assert not User.objects.filter(email="nova@example.test").exists()


def test_recovery_link_rule_needs_the_target_in_that_location(
    secretariat, location, other_location
):
    elsewhere = staff(other_location, Role.PROFESSIONAL, "fora")
    here = staff(location, Role.PROFESSIONAL, "aqui")

    assert permissions.can_send_recovery_link(secretariat, here, location)
    assert not permissions.can_send_recovery_link(secretariat, elsewhere, location)
    assert not permissions.can_send_recovery_link(secretariat, elsewhere, other_location)
