import pytest
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import translation

from core.models import Location, User
from core.tests.helpers import days_from_today

pytestmark = pytest.mark.django_db


def test_user_model_is_the_custom_one():
    assert get_user_model() is User
    assert User.USERNAME_FIELD == "email"


def test_email_is_stored_in_lowercase(make_user):
    assert make_user("Pessoa@Example.TEST").email == "pessoa@example.test"


def test_email_is_unique_regardless_of_case(make_user):
    make_user("pessoa@example.test")

    with pytest.raises(IntegrityError), transaction.atomic():
        make_user("PESSOA@example.test")


def test_form_validation_reports_duplicate_email_regardless_of_case(make_user):
    make_user("pessoa@example.test")
    duplicate = User(email="PESSOA@example.test", full_name="Outra", password="unused")

    with pytest.raises(ValidationError) as error:
        duplicate.full_clean()

    assert "email" in error.value.message_dict


def test_database_rejects_uppercase_email_written_around_the_model(make_user):
    user = make_user()

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(pk=user.pk).update(email="PESSOA@example.test")


def test_login_works_with_any_capitalisation_of_the_email(make_user, location, make_professional):
    user = make_user("pessoa@example.test", password="palavra-longa-e-rara")
    make_professional(user, location, start_date=days_from_today(-1), end_date=None)

    assert authenticate(username="PESSOA@Example.test", password="palavra-longa-e-rara") == user


def test_login_fails_with_wrong_password(make_user):
    make_user("pessoa@example.test", password="palavra-longa-e-rara")

    assert authenticate(username="pessoa@example.test", password="errada") is None


def test_login_fails_for_deactivated_account(make_user):
    make_user("pessoa@example.test", password="palavra-longa-e-rara", is_active=False)

    assert authenticate(username="pessoa@example.test", password="palavra-longa-e-rara") is None


def test_account_without_password_cannot_log_in(make_user):
    user = make_user("pessoa@example.test")

    assert not user.has_usable_password()
    assert authenticate(username="pessoa@example.test", password="") is None


def test_is_staff_follows_is_superuser(make_user, admin_user):
    assert admin_user.is_staff is True
    assert make_user().is_staff is False


def test_model_names_use_european_portuguese_translations():
    with translation.override("pt-pt"):
        assert str(Location._meta.verbose_name) == "polo"
        assert str(User._meta.get_field("email").verbose_name) == "endereço de e-mail"


def test_models_and_migrations_are_in_sync():
    call_command("makemigrations", check=True, dry_run=True, verbosity=0)
