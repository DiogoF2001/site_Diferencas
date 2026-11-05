"""A role that requires 2FA, given to someone who already has an account (plan, section 5)."""

import re
import smtplib

import pytest
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from core import accounts
from core.models import AuditEvent, Membership, Role, Subrole, User
from core.tests.helpers import days_from_today, login_verified, make_account, make_member, today
from core.tests.test_two_factor import MISSING, current_code, is_signed_in, log_in, with_password

pytestmark = pytest.mark.django_db

Action = AuditEvent.Action


def person_with_password(location, role=Role.PROFESSIONAL, name="acumula", *, signed_in=True):
    user = with_password(make_account(name))
    make_member(user, location, role)
    if signed_in:
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
    return user


def staff_role(user, location, *, start, role=Role.SECRETARIAT):
    return make_member(user, location, role, start=start, end=None)


def add(client, location, email, role=Role.SECRETARIAT, start=0):
    return client.post(
        reverse("member_add", args=[location.pk]),
        {
            "email": email,
            "full_name": "",
            "role": role,
            "subrole": Subrole.RESIDENT if role == Role.PROFESSIONAL else "",
            "start_date": days_from_today(start).isoformat(),
            "end_date": "",
        },
    )


def _request():
    return RequestFactory().get("/", HTTP_HOST="testserver")


def two_factor_link_in(message):
    return re.search(r"https?://\S+(/conta/2fa/link/\S+/)", message.body).group(1)


@pytest.fixture
def coordination(client, location):
    user = make_account("coordenacao")
    make_member(user, location, Role.COORDINATION)
    login_verified(client, user)
    return user


# 1. Assigning the role sends the link


@pytest.mark.parametrize("role", [Role.SECRETARIAT, Role.COORDINATION])
def test_staff_role_for_an_existing_account_sends_the_2fa_link(
    client, location, coordination, mailoutbox, role
):
    person = person_with_password(location)

    response = add(client, location, person.email, role, start=5)

    assert response.status_code == 302
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [person.email]
    assert "/conta/2fa/link/" in mailoutbox[0].body
    event = AuditEvent.objects.get(action=Action.TWO_FACTOR_LINK_SENT)
    assert (event.actor, event.target, event.location) == (coordination, person, location)
    page = client.get(reverse("member_list", args=[location.pk])).content.decode()
    assert "foi enviado o link" in page


def test_professional_role_sends_nothing(client, location, coordination, mailoutbox):
    person = person_with_password(location, name="outra")
    other = Membership.objects.get(user=person)
    other.delete()

    add(client, location, person.email, Role.PROFESSIONAL)

    assert mailoutbox == []
    assert not AuditEvent.objects.filter(action=Action.TWO_FACTOR_LINK_SENT).exists()


def test_staff_role_for_someone_with_a_device_sends_nothing(
    client, location, coordination, mailoutbox
):
    person = person_with_password(location)
    TOTPDevice.objects.create(user=person, name="default", confirmed=True)

    add(client, location, person.email)

    assert mailoutbox == []


def test_staff_role_for_an_account_without_a_password_resends_the_invitation(
    client, location, other_location, coordination, mailoutbox
):
    person = make_account("convidada")
    make_member(person, other_location, Role.PROFESSIONAL)

    add(client, location, person.email)

    assert len(mailoutbox) == 1
    assert "/conta/definir/" in mailoutbox[0].body
    assert AuditEvent.objects.filter(action=Action.INVITATION_SENT, target=person).exists()


def test_staff_role_for_a_deactivated_account_sends_nothing(
    client, location, coordination, mailoutbox
):
    person = person_with_password(location)
    person.is_active = False
    person.save()

    add(client, location, person.email)

    assert person.memberships.filter(role=Role.SECRETARIAT).exists()
    assert mailoutbox == []


WARNING = "Não foi possível enviar o link do 2FA. Volte a enviá-lo mais tarde."


def fail_smtp(monkeypatch):
    def fail(*args, **kwargs):
        raise smtplib.SMTPException("down")

    monkeypatch.setattr("core.accounts.send_mail", fail)


def test_limit_reached_still_gives_the_role_and_audits_it(
    client, location, coordination, mailoutbox
):
    person = person_with_password(location)
    for _sent in range(3):
        accounts.send_password_link(_request(), person)
    mailoutbox.clear()

    response = add(client, location, person.email)

    assert response.status_code == 302
    assert person.memberships.filter(role=Role.SECRETARIAT).exists()
    assert mailoutbox == []
    event = AuditEvent.objects.get(action=Action.TWO_FACTOR_LINK_FAILED)
    assert (event.actor, event.target, event.location) == (coordination, person, location)
    assert event.details == {"reason": "limit"}
    page = client.get(response.url).content.decode()
    assert WARNING in page
    assert "Enviar link do 2FA" in page


def test_smtp_error_still_gives_the_role_and_audits_it(client, location, coordination, monkeypatch):
    person = person_with_password(location)
    fail_smtp(monkeypatch)

    response = add(client, location, person.email)

    assert response.status_code == 302
    assert person.memberships.filter(role=Role.SECRETARIAT).exists()
    event = AuditEvent.objects.get(action=Action.TWO_FACTOR_LINK_FAILED)
    assert event.details == {"reason": "smtp"}
    assert not AuditEvent.objects.filter(action=Action.TWO_FACTOR_LINK_SENT).exists()
    assert WARNING in client.get(response.url).content.decode()


def test_smtp_error_resending_an_invitation_also_keeps_the_role(
    client, location, other_location, coordination, monkeypatch
):
    person = make_account("convidada")
    make_member(person, other_location, Role.PROFESSIONAL)
    fail_smtp(monkeypatch)

    assert add(client, location, person.email).status_code == 302
    assert person.memberships.filter(location=location).exists()
    assert AuditEvent.objects.filter(action=Action.TWO_FACTOR_LINK_FAILED).exists()


def test_new_account_invitation_failure_still_leaves_nothing(
    client, location, coordination, monkeypatch
):
    fail_smtp(monkeypatch)

    response = add(client, location, "nova@example.test")

    assert response.status_code == 200
    assert not User.objects.filter(email="nova@example.test").exists()
    assert not AuditEvent.objects.filter(action=Action.TWO_FACTOR_LINK_FAILED).exists()


def test_send_link_button_sends_the_2fa_link_after_a_failure(
    client, location, coordination, monkeypatch, mailoutbox
):
    person = person_with_password(location)
    with monkeypatch.context() as patch:
        fail_smtp(patch)
        add(client, location, person.email)

    client.post(reverse("account_send_link", args=[location.pk, person.pk]))

    assert len(mailoutbox) == 1
    assert "/conta/2fa/link/" in mailoutbox[0].body
    assert AuditEvent.objects.filter(action=Action.TWO_FACTOR_LINK_SENT, target=person).exists()
    assert person.has_usable_password()


def test_send_link_button_sends_a_password_link_when_no_2fa_is_due(
    client, location, coordination, mailoutbox
):
    person = person_with_password(location)

    page = client.get(reverse("member_list", args=[location.pk])).content.decode()
    client.post(reverse("account_send_link", args=[location.pk, person.pk]))

    assert "Enviar link do 2FA" not in page
    assert "/conta/definir/" in mailoutbox[0].body


def test_secretariat_of_another_location_cannot_send_the_2fa_link(
    client, location, other_location, monkeypatch, mailoutbox
):
    person = person_with_password(location)
    staff_role(person, location, start=3)
    other = make_account("secretariado-b")
    make_member(other, other_location, Role.SECRETARIAT)
    login_verified(client, other)

    response = client.post(reverse("account_send_link", args=[other_location.pk, person.pk]))

    assert response.status_code == 404
    assert mailoutbox == []


def test_2fa_links_use_up_the_limit_for_recovery_links(location, mailoutbox):
    person = person_with_password(location)
    membership = staff_role(person, location, start=3)
    for _sent in range(3):
        accounts.send_two_factor_link(_request(), membership)

    with pytest.raises(accounts.EmailLimitReached):
        accounts.send_password_link(_request(), person)


def test_backoffice_sends_the_link_when_creating_a_staff_role(
    client, admin_user, location, mailoutbox
):
    person = person_with_password(location)
    login_verified(client, admin_user)

    client.post(
        reverse("admin:core_membership_add"),
        {
            "user": person.pk,
            "location": location.pk,
            "role": Role.COORDINATION,
            "subrole": "",
            "start_date": today().isoformat(),
        },
    )

    assert len(mailoutbox) == 1
    event = AuditEvent.objects.get(action=Action.TWO_FACTOR_LINK_SENT)
    assert event.actor == admin_user


def test_backoffice_keeps_the_role_and_warns_when_the_link_fails(
    client, admin_user, location, monkeypatch
):
    person = person_with_password(location)
    login_verified(client, admin_user)
    fail_smtp(monkeypatch)

    response = client.post(
        reverse("admin:core_membership_add"),
        {
            "user": person.pk,
            "location": location.pk,
            "role": Role.SECRETARIAT,
            "subrole": "",
            "start_date": today().isoformat(),
        },
        follow=True,
    )

    assert person.memberships.filter(role=Role.SECRETARIAT).exists()
    assert WARNING in response.content.decode()
    event = AuditEvent.objects.get(action=Action.TWO_FACTOR_LINK_FAILED)
    assert (event.actor, event.details) == (admin_user, {"reason": "smtp"})


def test_backoffice_sends_the_link_only_when_the_role_changes(
    client, admin_user, location, mailoutbox
):
    person = person_with_password(location)
    membership = Membership.objects.get(user=person)
    login_verified(client, admin_user)
    url = reverse("admin:core_membership_change", args=[membership.pk])

    def save(role, subrole):
        client.post(
            url,
            {
                "user": person.pk,
                "location": location.pk,
                "role": role,
                "subrole": subrole,
                "start_date": membership.start_date.isoformat(),
                "end_date": membership.end_date.isoformat(),
            },
        )

    save(Role.PROFESSIONAL, Subrole.INTERN)
    assert mailoutbox == []
    save(Role.SECRETARIAT, "")
    assert len(mailoutbox) == 1
    save(Role.SECRETARIAT, "")
    assert len(mailoutbox) == 1


# The 2FA link


def sent_link(location, person, start=5):
    membership = staff_role(person, location, start=start)
    accounts.send_two_factor_link(_request(), membership)
    return membership


@pytest.fixture
def linked(location, mailoutbox):
    person = person_with_password(location)
    sent_link(location, person)
    return person, two_factor_link_in(mailoutbox[-1])


def test_2fa_link_asks_for_the_password_then_sets_it_up(client, linked):
    person, link = linked
    assert "Palavra-passe" in client.get(link).content.decode()

    response = client.post(link, {"password": "uma-palavra-passe-nova-e-longa"})

    assert response.url == reverse("two_factor_enrol")
    client.get(response.url)
    device = TOTPDevice.objects.get(user=person, confirmed=False)
    done = client.post(reverse("two_factor_enrol"), {"token": current_code(device)})
    assert done.url == reverse("login")
    device.refresh_from_db()
    assert device.confirmed
    # Done: the link no longer works.
    assert Client().get(link).status_code == 400


def test_2fa_link_with_a_wrong_password_is_refused_and_counted(client, linked):
    person, link = linked

    response = client.post(link, {"password": "errada-errada-errada"})

    assert response.status_code == 200
    assert client.get(reverse("two_factor_enrol")).status_code == 400
    event = AuditEvent.objects.get(action=Action.LOGIN_FAILED)
    assert (event.target, event.email) == (person, person.email)


def test_2fa_link_respects_the_login_lockout(client, linked):
    _person, link = linked
    for _attempt in range(5):
        client.post(link, {"password": "errada-errada-errada"})

    response = client.post(link, {"password": "uma-palavra-passe-nova-e-longa"})

    assert response.status_code == 200
    assert "Demasiadas tentativas" in response.content.decode()
    assert client.get(reverse("two_factor_enrol")).status_code == 400


def test_2fa_link_still_works_after_signing_in_elsewhere(client, linked):
    person, link = linked
    person.last_login = timezone.now()
    person.save(update_fields=["last_login"])

    assert client.get(link).status_code == 200


def test_2fa_link_ends_with_a_new_password(client, linked):
    person, link = linked
    with_password(person, "outra-palavra-passe-longa")

    assert client.get(link).status_code == 400


def test_2fa_link_ends_when_the_account_is_deactivated(client, linked):
    person, link = linked
    person.is_active = False
    person.save()

    assert client.get(link).status_code == 400


def test_2fa_link_ends_when_the_role_is_removed(client, linked):
    person, link = linked
    person.memberships.filter(role=Role.SECRETARIAT).delete()

    assert client.get(link).status_code == 400


def test_2fa_link_with_a_forged_token_is_refused(client, linked):
    _person, link = linked

    assert client.get(link[:-4] + "abc/").status_code == 400


# Notice before the role starts


def test_upcoming_staff_role_shows_a_notice(client, location):
    person = person_with_password(location)
    staff_role(person, location, start=4)
    client.force_login(person)

    page = client.get(reverse("home")).content.decode()

    assert "exige autenticação de dois fatores" in page
    assert reverse("two_factor_setup") in page


def test_no_notice_without_an_upcoming_staff_role(client, location):
    client.force_login(person_with_password(location))

    assert "exige autenticação de dois fatores" not in client.get(reverse("home")).content.decode()


def test_no_notice_once_2fa_is_on(client, location):
    person = person_with_password(location)
    staff_role(person, location, start=4)
    login_verified(client, person)

    assert "exige autenticação de dois fatores" not in client.get(reverse("home")).content.decode()


def test_setting_it_up_before_the_role_sends_a_confirmation(client, location, mailoutbox):
    person = person_with_password(location)
    staff_role(person, location, start=4)
    client.force_login(person)
    client.get(reverse("two_factor_setup"))
    device = TOTPDevice.objects.get(user=person)

    client.post(reverse("two_factor_setup"), {"token": current_code(device)})

    device.refresh_from_db()
    assert device.confirmed
    assert len(mailoutbox) == 1
    assert "se não foi" in mailoutbox[0].body.lower()


# 2. Grace period after the role starts


@pytest.mark.parametrize("start", [0, -6])
def test_within_the_grace_period_staff_sign_in_only_to_set_up_2fa(client, location, start):
    person = person_with_password(location)
    staff_role(person, location, start=start)

    assert log_in(client, person).status_code == 302
    assert is_signed_in(client)
    assert client.get(reverse("home")).url.startswith(reverse("two_factor_setup"))
    members = client.get(reverse("member_list", args=[location.pk]))
    assert members.url.startswith(reverse("two_factor_setup"))
    assert client.get(reverse("two_factor_setup")).status_code == 200


def test_day_8_needs_a_new_link(client, location):
    person = person_with_password(location)
    staff_role(person, location, start=-7)

    response = log_in(client, person)

    assert MISSING in response.content.decode()
    assert not is_signed_in(client)


def test_grace_period_is_configurable(client, location, settings):
    settings.PORTAL_TWO_FACTOR_GRACE_DAYS = 10
    person = person_with_password(location)
    staff_role(person, location, start=-9)

    assert log_in(client, person).status_code == 302
    assert is_signed_in(client)


def test_grace_counts_from_the_earliest_active_staff_role(client, location, other_location):
    person = person_with_password(location)
    staff_role(person, location, start=-10)
    staff_role(person, other_location, start=-1, role=Role.COORDINATION)

    assert MISSING in log_in(client, person).content.decode()


def test_an_account_that_never_signed_in_has_no_grace(client, location):
    person = person_with_password(location, signed_in=False)
    staff_role(person, location, start=0)

    assert MISSING in log_in(client, person).content.decode()
    assert not is_signed_in(client)


def test_a_deactivated_account_has_no_grace(client, location):
    person = person_with_password(location)
    staff_role(person, location, start=0)
    person.is_active = False
    person.save()

    response = log_in(client, person)

    assert "não tem acesso" in response.content.decode()
    assert not is_signed_in(client)


def test_a_grace_session_ends_on_day_8(client, location):
    person = person_with_password(location)
    membership = staff_role(person, location, start=0)
    log_in(client, person)
    Membership.objects.filter(pk=membership.pk).update(start_date=days_from_today(-7))

    assert client.get(reverse("two_factor_setup")).url == reverse("login")
    assert not is_signed_in(client)


def test_setting_it_up_in_the_grace_period_sends_a_confirmation(client, location, mailoutbox):
    person = person_with_password(location)
    staff_role(person, location, start=-2)
    log_in(client, person)
    client.get(reverse("two_factor_setup"))
    device = TOTPDevice.objects.get(user=person)

    response = client.post(reverse("two_factor_setup"), {"token": current_code(device)})

    assert response.url == reverse("home")
    assert client.get(reverse("member_list", args=[location.pk])).status_code == 200
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [person.email]
    assert "contacte o secretariado" in mailoutbox[0].body
    event = AuditEvent.objects.get(action=Action.TWO_FACTOR_NOTICE_SENT)
    assert (event.actor, event.target) == (person, person)


def test_a_failed_confirmation_email_does_not_undo_2fa(client, location, monkeypatch):
    person = person_with_password(location)
    staff_role(person, location, start=-2)
    log_in(client, person)
    client.get(reverse("two_factor_setup"))
    device = TOTPDevice.objects.get(user=person)

    fail_smtp(monkeypatch)
    client.post(reverse("two_factor_setup"), {"token": current_code(device)})

    device.refresh_from_db()
    assert device.confirmed
    assert not AuditEvent.objects.filter(action=Action.TWO_FACTOR_NOTICE_SENT).exists()
    event = AuditEvent.objects.get(action=Action.TWO_FACTOR_NOTICE_FAILED)
    assert (event.actor, event.target, event.details) == (person, person, {"reason": "smtp"})


# 3. The admin is unchanged


def test_admin_setup_sends_no_confirmation(client, admin_user, mailoutbox):
    client.force_login(admin_user)
    client.get(reverse("two_factor_setup"))
    device = TOTPDevice.objects.get(user=admin_user)

    client.post(reverse("two_factor_setup"), {"token": current_code(device)})

    device.refresh_from_db()
    assert device.confirmed
    assert mailoutbox == []


def test_admin_gets_no_2fa_link(admin_user, location, mailoutbox):
    membership = Membership(user=admin_user, location=location, role=Role.SECRETARIAT)
    membership.start_date = today()

    assert accounts.send_two_factor_link(_request(), membership) is None
    assert mailoutbox == []
    assert User.objects.filter(pk=admin_user.pk, totpdevice__isnull=True).exists()
