import time

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from core import accounts
from core.models import AuditEvent, Role
from core.tests.helpers import login_verified, make_account, make_member
from core.tokens import password_link_token
from core.views.two_factor import ENROL_MINUTES

pytestmark = pytest.mark.django_db

Action = AuditEvent.Action
PASSWORD = "uma-palavra-passe-nova-e-longa"
MISSING = "precisa de ativar a autenticação de dois fatores"


def current_code(device):
    totp = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
    return f"{totp.token():06d}"


def member(location, role):
    user = make_account(role)
    make_member(user, location, role)
    return user


def link_path(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    return reverse("password_set", args=[uid, password_link_token.make_token(user)])


def set_password_by_link(client, user, password=PASSWORD):
    form_page = client.get(link_path(user), follow=True)
    set_url = form_page.redirect_chain[-1][0]
    return client.post(set_url, {"new_password1": password, "new_password2": password})


def log_in(client, user, password=PASSWORD):
    return client.post(reverse("login"), {"username": user.email, "password": password})


def with_password(user, password=PASSWORD):
    user.set_password(password)
    user.save()
    return user


def is_signed_in(client):
    return "_auth_user_id" in client.session


# Staff without a device: never with the password alone


@pytest.mark.parametrize("role", [Role.SECRETARIAT, Role.COORDINATION])
def test_staff_without_a_device_cannot_log_in_with_the_password(client, location, role):
    person = with_password(member(location, role))

    response = log_in(client, person)

    assert response.status_code == 200
    assert MISSING in response.content.decode()
    assert not is_signed_in(client)


def test_staff_without_a_device_and_a_wrong_password_learn_nothing_more(client, location):
    person = with_password(member(location, Role.SECRETARIAT))

    page = log_in(client, person, "outra-palavra-passe").content.decode()

    assert MISSING not in page
    assert not is_signed_in(client)


def test_staff_with_a_device_log_in_and_are_asked_for_the_code(client, location):
    person = with_password(member(location, Role.SECRETARIAT))
    TOTPDevice.objects.create(user=person, name="default", confirmed=True)

    response = log_in(client, person)

    assert response.status_code == 302
    assert client.get(reverse("home")).url.startswith(reverse("two_factor_verify"))


def test_an_unconfirmed_device_does_not_count(client, location):
    person = with_password(member(location, Role.COORDINATION))
    TOTPDevice.objects.create(user=person, name="default", confirmed=False)

    assert MISSING in log_in(client, person).content.decode()


def test_professional_without_a_device_logs_in(client, location):
    person = with_password(member(location, Role.PROFESSIONAL))

    log_in(client, person)

    assert is_signed_in(client)


def test_admin_without_a_device_logs_in_and_sets_it_up(client, admin_user):
    response = client.post(
        reverse("login"), {"username": admin_user.email, "password": "palavra-longa-e-rara"}
    )

    assert response.status_code == 302
    assert client.get(reverse("home")).url.startswith(reverse("two_factor_setup"))


@pytest.mark.parametrize("role", [Role.SECRETARIAT, Role.COORDINATION])
def test_staff_session_without_a_device_is_signed_out(client, location, role):
    # A password-only session, as when a staff role starts during it.
    client.force_login(member(location, role))

    response = client.get(reverse("member_list", args=[location.pk]))

    assert response.url == reverse("login")
    assert not is_signed_in(client)
    assert MISSING in client.get(response.url).content.decode()


def test_staff_cannot_open_the_signed_in_setup_without_a_device(client, location):
    person = member(location, Role.SECRETARIAT)
    client.force_login(person)

    response = client.get(reverse("two_factor_setup"))

    assert response.url == reverse("login")
    assert not TOTPDevice.objects.filter(user=person).exists()


def test_resetting_staff_two_factor_ends_their_session(client, location):
    person = member(location, Role.SECRETARIAT)
    login_verified(client, person)
    assert client.get(reverse("home")).status_code == 200

    TOTPDevice.objects.filter(user=person).delete()

    assert client.get(reverse("home")).url == reverse("login")
    assert not is_signed_in(client)


def test_admin_must_set_up_two_factor(client, admin_user):
    client.force_login(admin_user)

    assert client.get(reverse("home")).url.startswith(reverse("two_factor_setup"))


def test_professional_without_a_device_is_not_forced(client, location):
    client.force_login(member(location, Role.PROFESSIONAL))

    assert client.get(reverse("home")).status_code == 200


def test_future_staff_role_does_not_force_two_factor_yet(client, location):
    person = member(location, Role.PROFESSIONAL)
    make_member(person, location, Role.SECRETARIAT, start=5, end=None)
    client.force_login(person)

    assert client.get(reverse("home")).status_code == 200


def test_anyone_with_a_device_must_enter_the_code(client, location):
    person = member(location, Role.PROFESSIONAL)
    TOTPDevice.objects.create(user=person, name="default", confirmed=True)
    client.force_login(person)

    response = client.get(reverse("home"))

    assert response.url.startswith(reverse("two_factor_verify"))


def test_setup_with_the_right_code_turns_two_factor_on(client, admin_user):
    client.force_login(admin_user)
    page = client.get(reverse("two_factor_setup"))
    assert "<svg" in page.content.decode()
    device = TOTPDevice.objects.get(user=admin_user)
    assert not device.confirmed

    response = client.post(
        reverse("two_factor_setup"),
        {"token": current_code(device), "next": reverse("admin:index")},
    )

    assert response.status_code == 302
    assert response.url == reverse("admin:index")
    device.refresh_from_db()
    assert device.confirmed
    assert client.get(reverse("admin:index")).status_code == 200
    assert AuditEvent.objects.filter(action=Action.TWO_FACTOR_ENABLED, target=admin_user).exists()


def test_professional_may_turn_two_factor_on_after_signing_in(client, location):
    person = member(location, Role.PROFESSIONAL)
    client.force_login(person)
    client.get(reverse("two_factor_setup"))
    device = TOTPDevice.objects.get(user=person)

    client.post(reverse("two_factor_setup"), {"token": current_code(device)})

    device.refresh_from_db()
    assert device.confirmed
    assert client.get(reverse("home")).status_code == 200


def test_setup_with_a_wrong_code_leaves_it_off(client, admin_user):
    client.force_login(admin_user)
    client.get(reverse("two_factor_setup"))

    client.post(reverse("two_factor_setup"), {"token": "000000"})

    assert not TOTPDevice.objects.get(user=admin_user).confirmed
    assert client.get(reverse("home")).url.startswith(reverse("two_factor_setup"))


def test_setup_is_refused_once_a_device_exists(client, location):
    person = member(location, Role.PROFESSIONAL)
    login_verified(client, person)

    response = client.get(reverse("two_factor_setup"))

    assert response.status_code == 302
    assert TOTPDevice.objects.filter(user=person).count() == 1


def test_verify_with_the_right_code_opens_the_portal(client, location):
    person = member(location, Role.COORDINATION)
    device = TOTPDevice.objects.create(user=person, name="default", confirmed=True)
    client.force_login(person)
    key_before = client.session.session_key

    response = client.post(reverse("two_factor_verify"), {"token": current_code(device)})

    assert response.url == reverse("home")
    assert client.get(reverse("home")).status_code == 200
    assert client.session.session_key != key_before


def test_verify_with_a_wrong_code_is_refused_and_audited(client, location):
    person = member(location, Role.COORDINATION)
    TOTPDevice.objects.create(user=person, name="default", confirmed=True)
    client.force_login(person)

    response = client.post(reverse("two_factor_verify"), {"token": "000000"})

    assert response.status_code == 200
    assert client.get(reverse("home")).url.startswith(reverse("two_factor_verify"))
    assert AuditEvent.objects.filter(action=Action.TWO_FACTOR_FAILED, target=person).exists()


def test_a_code_cannot_be_used_twice(client, location):
    person = member(location, Role.COORDINATION)
    device = TOTPDevice.objects.create(user=person, name="default", confirmed=True)
    code = current_code(device)
    client.force_login(person)
    client.post(reverse("two_factor_verify"), {"token": code})

    other = Client()
    other.force_login(person)
    other.post(reverse("two_factor_verify"), {"token": code})

    assert other.get(reverse("home")).url.startswith(reverse("two_factor_verify"))


def test_verify_does_not_redirect_to_another_site(client, location):
    person = member(location, Role.COORDINATION)
    device = TOTPDevice.objects.create(user=person, name="default", confirmed=True)
    client.force_login(person)

    response = client.post(
        reverse("two_factor_verify"),
        {"token": current_code(device), "next": "https://example.com/"},
    )

    assert response.url == reverse("home")


def test_reset_2fa_command_removes_the_devices_and_is_audited(admin_user):
    TOTPDevice.objects.create(user=admin_user, name="default", confirmed=True)

    call_command("reset_2fa", "ADMIN@example.test")

    assert not TOTPDevice.objects.filter(user=admin_user).exists()
    event = AuditEvent.objects.get(action=Action.TWO_FACTOR_RESET)
    assert event.target == admin_user
    assert event.actor is None


# Setting up 2FA in the link flow


def enrolment_device(client):
    page = client.get(reverse("two_factor_enrol"))
    assert page.status_code == 200
    assert "<svg" in page.content.decode()
    return TOTPDevice.objects.get(confirmed=False)


@pytest.mark.parametrize("role", [Role.SECRETARIAT, Role.COORDINATION])
def test_invited_staff_set_up_two_factor_right_after_the_password(client, location, role):
    person = member(location, role)

    response = set_password_by_link(client, person)

    assert response.url == reverse("two_factor_enrol")
    assert not is_signed_in(client)
    device = enrolment_device(client)
    assert device.user == person

    response = client.post(reverse("two_factor_enrol"), {"token": current_code(device)})

    assert response.url == reverse("login")
    device.refresh_from_db()
    assert device.confirmed
    assert AuditEvent.objects.filter(action=Action.TWO_FACTOR_ENABLED, target=person).exists()
    # Signing in now takes the password and then a code.
    assert log_in(client, person).status_code == 302
    assert client.get(reverse("home")).url.startswith(reverse("two_factor_verify"))


def test_staff_recovering_the_password_also_set_up_two_factor(client, location):
    person = with_password(member(location, Role.SECRETARIAT), "a-antiga-palavra-passe")

    assert set_password_by_link(client, person).url == reverse("two_factor_enrol")


def test_staff_invited_for_a_future_role_set_it_up_too(client, location):
    person = make_account("futura")
    make_member(person, location, Role.SECRETARIAT, start=5, end=None)

    assert set_password_by_link(client, person).url == reverse("two_factor_enrol")


def test_professional_link_ends_at_the_password(client, location):
    person = member(location, Role.PROFESSIONAL)

    assert set_password_by_link(client, person).url == reverse("login")
    assert client.get(reverse("two_factor_enrol")).status_code == 400
    assert not TOTPDevice.objects.exists()


def test_staff_with_a_device_only_set_the_password(client, location):
    person = member(location, Role.SECRETARIAT)
    TOTPDevice.objects.create(user=person, name="default", confirmed=True)

    assert set_password_by_link(client, person).url == reverse("login")
    assert client.get(reverse("two_factor_enrol")).status_code == 400


def test_enrolment_with_a_wrong_code_leaves_it_off_and_is_audited(client, location):
    person = member(location, Role.SECRETARIAT)
    set_password_by_link(client, person)
    enrolment_device(client)

    response = client.post(reverse("two_factor_enrol"), {"token": "000000"})

    assert response.status_code == 200
    assert not TOTPDevice.objects.get(user=person).confirmed
    event = AuditEvent.objects.get(action=Action.TWO_FACTOR_FAILED, target=person)
    assert event.actor is None


def test_enrolment_is_throttled_after_wrong_codes(client, location):
    person = member(location, Role.SECRETARIAT)
    set_password_by_link(client, person)
    device = enrolment_device(client)
    for _attempt in range(3):
        client.post(reverse("two_factor_enrol"), {"token": "000000"})

    client.post(reverse("two_factor_enrol"), {"token": current_code(device)})

    device.refresh_from_db()
    assert not device.confirmed


def test_enrolment_needs_the_session_that_used_the_link(client, location):
    person = member(location, Role.SECRETARIAT)
    set_password_by_link(client, person)
    device = enrolment_device(client)

    other = Client()
    response = other.post(reverse("two_factor_enrol"), {"token": current_code(device)})

    assert response.status_code == 400
    device.refresh_from_db()
    assert not device.confirmed


def test_enrolment_closes_after_its_window(client, location, monkeypatch):
    person = member(location, Role.SECRETARIAT)
    set_password_by_link(client, person)
    device = enrolment_device(client)
    later = time.time() + ENROL_MINUTES * 60 + 1
    monkeypatch.setattr("core.views.two_factor.time.time", lambda: later)

    response = client.post(reverse("two_factor_enrol"), {"token": current_code(device)})

    assert response.status_code == 400
    device.refresh_from_db()
    assert not device.confirmed


def test_abandoned_enrolment_needs_a_new_link(client, location):
    person = member(location, Role.SECRETARIAT)
    old_link = link_path(person)
    set_password_by_link(client, person)
    enrolment_device(client)

    # Leaving halfway: the password alone does not sign in, and the old link is spent.
    assert MISSING in log_in(Client(), person).content.decode()
    assert "já não é válido" in Client().get(old_link, follow=True).content.decode()

    # A new link starts over, and ends the step opened by the first one.
    person.refresh_from_db()
    fresh = Client()
    assert set_password_by_link(fresh, person, "outra-palavra-passe-longa").url == reverse(
        "two_factor_enrol"
    )
    assert client.get(reverse("two_factor_enrol")).status_code == 400
    device = enrolment_device(fresh)
    fresh.post(reverse("two_factor_enrol"), {"token": current_code(device)})
    device.refresh_from_db()
    assert device.confirmed


def test_enrolment_without_a_link_is_refused(client, location):
    member(location, Role.SECRETARIAT)

    assert client.get(reverse("two_factor_enrol")).status_code == 400
    assert not TOTPDevice.objects.exists()


def test_enrolment_closes_when_the_account_is_deactivated(client, location):
    person = member(location, Role.SECRETARIAT)
    set_password_by_link(client, person)
    device = enrolment_device(client)
    person.is_active = False
    person.save()

    response = client.post(reverse("two_factor_enrol"), {"token": current_code(device)})

    assert response.status_code == 400
    device.refresh_from_db()
    assert not device.confirmed


def test_after_a_reset_staff_set_it_up_again_through_a_link(client, location):
    coordination = member(location, Role.COORDINATION)
    person = with_password(member(location, Role.SECRETARIAT))
    TOTPDevice.objects.create(user=person, name="default", confirmed=True)
    accounts.reset_two_factor(coordination, person)

    assert MISSING in log_in(Client(), person).content.decode()
    assert set_password_by_link(client, person).url == reverse("two_factor_enrol")
