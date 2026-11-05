from io import StringIO

import pytest
from django.contrib.auth import authenticate
from django.core.management import CommandError, call_command

from core.models import User

pytestmark = pytest.mark.django_db

PASSWORD = "palavra-longa-e-rara"


@pytest.fixture
def admin_env(monkeypatch):
    monkeypatch.setenv("PORTAL_ADMIN_EMAIL", "Admin@Example.test")
    monkeypatch.setenv("PORTAL_ADMIN_PASSWORD", PASSWORD)
    monkeypatch.delenv("PORTAL_ADMIN_NAME", raising=False)
    return monkeypatch


def run():
    stdout, stderr = StringIO(), StringIO()
    call_command("ensure_admin", stdout=stdout, stderr=stderr)
    return stdout.getvalue() + stderr.getvalue()


def test_creates_the_admin_from_the_environment(admin_env):
    admin_env.setenv("PORTAL_ADMIN_NAME", "Conta técnica")

    run()

    admin = User.objects.get()
    assert admin.email == "admin@example.test"
    assert admin.full_name == "Conta técnica"
    assert admin.is_superuser
    assert admin.is_active
    assert authenticate(username="admin@example.test", password=PASSWORD) == admin


def test_never_prints_the_password(admin_env):
    assert PASSWORD not in run()
    assert PASSWORD not in run()


def test_running_again_changes_nothing(admin_env):
    run()
    before = User.objects.get()

    run()

    after = User.objects.get()
    assert after.pk == before.pk
    assert after.password == before.password


def test_running_again_does_not_undo_a_changed_password(admin_env):
    run()
    admin = User.objects.get()
    admin.set_password("outra-palavra-longa-e-rara")
    admin.save()

    run()

    assert authenticate(username="admin@example.test", password="outra-palavra-longa-e-rara")
    assert not authenticate(username="admin@example.test", password=PASSWORD)


def test_running_again_reactivates_the_admin(admin_env):
    run()
    User.objects.update(is_active=False)

    run()

    assert User.objects.get().is_active


@pytest.mark.parametrize("missing", ["PORTAL_ADMIN_EMAIL", "PORTAL_ADMIN_PASSWORD"])
def test_refuses_to_run_without_the_required_variables(admin_env, missing):
    admin_env.delenv(missing)

    with pytest.raises(CommandError):
        run()

    assert not User.objects.exists()


@pytest.mark.parametrize("password", ["curta", "123456789012345", "password1234"])
def test_refuses_a_weak_password(admin_env, password):
    admin_env.setenv("PORTAL_ADMIN_PASSWORD", password)

    with pytest.raises(CommandError) as error:
        run()

    assert password not in str(error.value)
    assert not User.objects.exists()


def test_refuses_an_invalid_email(admin_env):
    admin_env.setenv("PORTAL_ADMIN_EMAIL", "isto-nao-e-um-email")

    with pytest.raises(CommandError):
        run()

    assert not User.objects.exists()


def test_refuses_to_promote_an_existing_normal_account(admin_env, make_user):
    person = make_user("admin@example.test")

    with pytest.raises(CommandError):
        run()

    person.refresh_from_db()
    assert not person.is_superuser
    assert not person.has_usable_password()


def test_refuses_to_create_a_second_admin(admin_env, admin_user):
    admin_env.setenv("PORTAL_ADMIN_EMAIL", "outro@example.test")

    with pytest.raises(CommandError):
        run()

    assert User.objects.get() == admin_user
