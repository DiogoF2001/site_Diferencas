import datetime
import os

from django.utils import timezone
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice

from core.models import Membership, Mentorship, Role, Subrole, User

PRODUCTION_ENV = {
    "DJANGO_SECRET_KEY": "k3Y9-only-for-this-test-qP7xV2mZ8sL4tR6wN1bH5cJ0fD3gA9yU",
    "DJANGO_DEBUG": "0",
    "DJANGO_ALLOWED_HOSTS": "portal.example.test",
    "DB_NAME": "unused",
    "DB_USER": "unused",
    "DB_PASSWORD": "unused",
    "EMAIL_HOST": "smtp.example.test",
    "DEFAULT_FROM_EMAIL": "portal@example.test",
}


def subprocess_env(**overrides):
    """Environment for a child `manage.py`: no project settings except the given ones."""
    inherited = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DJANGO_", "DB_", "WORKER_", "EMAIL_", "DEFAULT_FROM_", "PORTAL_"))
    }
    return {**inherited, **overrides}


def today():
    return timezone.localdate()


def days_from_today(days):
    return today() + datetime.timedelta(days=days)


def make_account(name, **fields):
    """No password, so that creating hundreds of accounts in the matrix tests stays fast."""
    return User.objects.create_user(f"{name}@example.test", name, **fields)


def make_member(user, location, role, *, subrole="", start=-30, end=30):
    """An active membership by default; `start` and `end` are days from today, or None for `end`."""
    if role == Role.PROFESSIONAL and not subrole:
        subrole = Subrole.RESIDENT
    return Membership.objects.create(
        user=user,
        location=location,
        role=role,
        subrole=subrole,
        start_date=days_from_today(start),
        end_date=None if end is None else days_from_today(end),
    )


def make_mentorship(mentor, mentee, location, *, start=-30, end=30):
    return Mentorship.objects.create(
        mentor=mentor,
        mentee=mentee,
        location=location,
        start_date=days_from_today(start),
        end_date=None if end is None else days_from_today(end),
    )


def login_verified(client, user):
    """Sign in with the second factor already given, as after the code step."""
    device, _created = TOTPDevice.objects.get_or_create(
        user=user, name="default", defaults={"confirmed": True}
    )
    client.force_login(user)
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()
    return device
