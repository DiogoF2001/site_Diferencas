import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from core.models import AuditEvent, Role
from core.tests.helpers import login_verified, make_account, make_member

pytestmark = pytest.mark.django_db

Action = AuditEvent.Action


def current_code(device):
    totp = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
    return f"{totp.token():06d}"


def member(location, role):
    user = make_account(role)
    make_member(user, location, role)
    return user


@pytest.mark.parametrize("role", [Role.SECRETARIAT, Role.COORDINATION])
def test_staff_must_set_up_two_factor_before_anything_else(client, location, role):
    client.force_login(member(location, role))

    response = client.get(reverse("member_list", args=[location.pk]))

    assert response.status_code == 302
    assert response.url.startswith(reverse("two_factor_setup"))


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


def test_setup_with_the_right_code_turns_two_factor_on(client, location):
    person = member(location, Role.SECRETARIAT)
    client.force_login(person)
    page = client.get(reverse("two_factor_setup"))
    assert "<svg" in page.content.decode()
    device = TOTPDevice.objects.get(user=person)
    assert not device.confirmed

    response = client.post(
        reverse("two_factor_setup"),
        {"token": current_code(device), "next": reverse("member_list", args=[location.pk])},
    )

    assert response.status_code == 302
    assert response.url == reverse("member_list", args=[location.pk])
    device.refresh_from_db()
    assert device.confirmed
    assert client.get(reverse("member_list", args=[location.pk])).status_code == 200
    assert AuditEvent.objects.filter(action=Action.TWO_FACTOR_ENABLED, target=person).exists()


def test_setup_with_a_wrong_code_leaves_it_off(client, location):
    person = member(location, Role.SECRETARIAT)
    client.force_login(person)
    client.get(reverse("two_factor_setup"))

    client.post(reverse("two_factor_setup"), {"token": "000000"})

    assert not TOTPDevice.objects.get(user=person).confirmed
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
