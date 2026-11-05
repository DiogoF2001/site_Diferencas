import subprocess
import sys

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import translation

from core.tests.helpers import PRODUCTION_ENV, subprocess_env


def manage(*args, env):
    return subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=settings.BASE_DIR,
        env=subprocess_env(**env),
        capture_output=True,
        text=True,
        check=False,
    )


def test_language_and_time_zone():
    assert settings.LANGUAGE_CODE == "pt-pt"
    assert settings.LANGUAGES == [("pt-pt", "Português (Portugal)")]
    assert settings.TIME_ZONE == "Europe/Lisbon"
    assert settings.USE_TZ is True


def test_django_messages_use_european_portuguese():
    with translation.override("pt-pt"):
        try:
            validate_email("invalid")
        except ValidationError as error:
            assert "Introduza" in error.messages[0]
        else:
            raise AssertionError("expected a validation error")


def test_application_refuses_to_start_without_secret_key():
    env = {key: value for key, value in PRODUCTION_ENV.items() if key != "DJANGO_SECRET_KEY"}

    result = manage("check", env=env)

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_production_settings_pass_deploy_check_without_warnings():
    result = manage("check", "--deploy", "--fail-level", "WARNING", env=PRODUCTION_ENV)

    assert result.returncode == 0, result.stderr


def test_debug_settings_fail_deploy_check():
    result = manage(
        "check", "--deploy", "--fail-level", "WARNING", env={**PRODUCTION_ENV, "DJANGO_DEBUG": "1"}
    )

    assert result.returncode != 0
