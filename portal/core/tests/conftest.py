import datetime

import pytest

from core.models import Location, Membership, Role, Subrole, User

START = datetime.date(2026, 1, 1)
END = datetime.date(2026, 6, 30)


@pytest.fixture
def location():
    return Location.objects.create(name="Polo A")


@pytest.fixture
def other_location():
    return Location.objects.create(name="Polo B")


@pytest.fixture
def make_user():
    def make(email="pessoa@example.test", **fields):
        return User.objects.create_user(email, fields.pop("full_name", "Pessoa"), **fields)

    return make


@pytest.fixture
def admin_user():
    return User.objects.create_superuser("admin@example.test", "Admin", "palavra-longa-e-rara")


@pytest.fixture
def make_professional():
    def make(user, location, subrole=Subrole.RESIDENT, start_date=START, end_date=END):
        return Membership.objects.create(
            user=user,
            location=location,
            role=Role.PROFESSIONAL,
            subrole=subrole,
            start_date=start_date,
            end_date=end_date,
        )

    return make
