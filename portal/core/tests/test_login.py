import datetime

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from core.models import AuditEvent, Location, Role, Subrole
from core.tests.helpers import days_from_today, login_verified, make_account, make_member

pytestmark = pytest.mark.django_db

PASSWORD = "palavra-longa-e-rara"
Action = AuditEvent.Action


@pytest.fixture
def professional(location):
    user = make_account("profissional")
    user.set_password(PASSWORD)
    user.save()
    make_member(user, location, Role.PROFESSIONAL)
    return user


def log_in(client, email, password=PASSWORD):
    return client.post(reverse("login"), {"username": email, "password": password})


def is_signed_in(client):
    return "_auth_user_id" in client.session


def test_member_logs_in_with_email_in_any_case(client, professional):
    response = log_in(client, "PROFISSIONAL@example.test")

    assert response.status_code == 302
    assert response.url == reverse("home")
    assert is_signed_in(client)


def test_wrong_password_is_refused_and_audited(client, professional):
    response = log_in(client, professional.email, "errada-errada-errada")

    assert response.status_code == 200
    assert "E-mail ou palavra-passe incorretos" in response.content.decode()
    assert not is_signed_in(client)
    event = AuditEvent.objects.get(action=Action.LOGIN_FAILED)
    assert event.target == professional
    assert event.email == professional.email


def test_failed_login_for_an_unknown_address_is_audited_without_an_account(client):
    log_in(client, "Ninguem@example.test", "qualquer-coisa-aqui")

    event = AuditEvent.objects.get(action=Action.LOGIN_FAILED)
    assert event.target is None
    assert event.email == "ninguem@example.test"


def test_address_is_locked_after_too_many_failures(client, professional):
    for _attempt in range(settings.PORTAL_LOGIN_MAX_FAILURES):
        log_in(client, professional.email, "errada-errada-errada")

    response = log_in(client, professional.email)

    assert "Demasiadas tentativas" in response.content.decode()
    assert not is_signed_in(client)


def test_lockout_also_applies_to_unknown_addresses(client):
    for _attempt in range(settings.PORTAL_LOGIN_MAX_FAILURES):
        log_in(client, "ninguem@example.test", "errada-errada-errada")

    response = log_in(client, "ninguem@example.test")

    assert "Demasiadas tentativas" in response.content.decode()


def test_lockout_does_not_reach_other_addresses(client, professional, location):
    for _attempt in range(settings.PORTAL_LOGIN_MAX_FAILURES):
        log_in(client, "outra@example.test", "errada-errada-errada")

    assert log_in(client, professional.email).status_code == 302


def test_lockout_ends_after_the_window(client, professional, monkeypatch):
    for _attempt in range(settings.PORTAL_LOGIN_MAX_FAILURES):
        log_in(client, professional.email, "errada-errada-errada")
    # Rows cannot be changed, so the clock moves instead.
    later = timezone.now() + datetime.timedelta(minutes=settings.PORTAL_LOGIN_LOCKOUT_MINUTES + 1)

    monkeypatch.setattr(timezone, "now", lambda: later)

    assert log_in(client, professional.email).status_code == 302


def test_failures_before_the_window_do_not_count(client, professional):
    long_ago = timezone.now() - datetime.timedelta(
        minutes=settings.PORTAL_LOGIN_LOCKOUT_MINUTES + 1
    )
    for _attempt in range(settings.PORTAL_LOGIN_MAX_FAILURES):
        AuditEvent.objects.create(
            action=Action.LOGIN_FAILED, email=professional.email, created_at=long_ago
        )

    assert log_in(client, professional.email).status_code == 302


@pytest.mark.parametrize(
    ("start", "end"),
    [
        pytest.param(1, 30, id="membership yet to start"),
        pytest.param(-30, -1, id="membership ended yesterday"),
    ],
)
def test_without_an_active_membership_login_is_refused(client, location, start, end):
    person = make_account("pessoa")
    person.set_password(PASSWORD)
    person.save()
    make_member(person, location, Role.PROFESSIONAL, start=start, end=end)

    response = log_in(client, person.email)

    assert not is_signed_in(client)
    assert "não tem acesso ao portal" in response.content.decode()


def test_access_message_is_only_shown_with_the_right_password(client, location):
    person = make_account("pessoa")
    person.set_password(PASSWORD)
    person.save()
    make_member(person, location, Role.PROFESSIONAL, start=-30, end=-1)

    response = log_in(client, person.email, "errada-errada-errada")

    assert "não tem acesso" not in response.content.decode()


def test_intern_still_logs_in_on_the_last_day(client, location):
    intern = make_account("estagiaria")
    intern.set_password(PASSWORD)
    intern.save()
    make_member(intern, location, Role.PROFESSIONAL, subrole=Subrole.INTERN, start=-30, end=0)

    assert log_in(client, intern.email).status_code == 302


def test_membership_only_in_an_inactive_location_gives_no_access(client):
    closed = Location.objects.create(name="Polo fechado", is_active=False)
    person = make_account("pessoa")
    person.set_password(PASSWORD)
    person.save()
    make_member(person, closed, Role.PROFESSIONAL)

    log_in(client, person.email)

    assert not is_signed_in(client)


def test_deactivated_account_cannot_log_in(client, professional):
    professional.is_active = False
    professional.save()

    log_in(client, professional.email)

    assert not is_signed_in(client)


def test_admin_logs_in_without_memberships(client, admin_user):
    assert log_in(client, admin_user.email).status_code == 302


def test_session_ends_when_the_membership_ends(client, professional):
    client.force_login(professional)
    assert client.get(reverse("home")).status_code == 200

    professional.memberships.update(end_date=days_from_today(-1))

    response = client.get(reverse("home"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_session_ends_when_the_account_is_deactivated(client, professional):
    client.force_login(professional)
    professional.is_active = False
    professional.save()

    assert client.get(reverse("home")).url.startswith(reverse("login"))


def test_sessions_expire_after_a_working_day_and_with_the_browser():
    assert settings.SESSION_COOKIE_AGE == 8 * 3600
    assert settings.SESSION_EXPIRE_AT_BROWSER_CLOSE is True


def test_logout_needs_a_post(client, professional):
    client.force_login(professional)

    assert client.get(reverse("logout")).status_code == 405
    client.post(reverse("logout"))
    assert not is_signed_in(client)


def test_home_lists_only_the_persons_active_locations(client, professional, other_location):
    make_member(professional, other_location, Role.PROFESSIONAL, start=-30, end=-1)

    client.force_login(professional)
    page = client.get(reverse("home")).content.decode()

    assert "Polo A" in page
    assert "Polo B" not in page


def test_home_links_only_to_what_the_person_may_open(client, location, other_location):
    person = make_account("pessoa")
    make_member(person, location, Role.SECRETARIAT)
    make_member(person, other_location, Role.PROFESSIONAL)
    login_verified(client, person)

    page = client.get(reverse("home")).content.decode()

    assert reverse("member_list", args=[location.pk]) in page
    assert reverse("member_list", args=[other_location.pk]) not in page
    assert reverse("professional_list", args=[location.pk]) not in page
