import pytest
from django.contrib import admin
from django.contrib.auth.models import Group
from django.test import RequestFactory
from django.urls import NoReverseMatch, reverse

from core.models import Location, Membership, Role, User
from core.tests.helpers import login_verified

pytestmark = pytest.mark.django_db

PASSWORD = "palavra-longa-e-rara"


@pytest.fixture
def coordinator(make_user, location):
    user = make_user("coordenacao@example.test", password=PASSWORD)
    Membership.objects.create(user=user, location=location, role=Role.COORDINATION)
    return user


def is_redirect_to_login(response):
    return response.status_code == 302 and reverse("admin:login") in response.url


def test_admin_can_open_the_backoffice(client, admin_user):
    login_verified(client, admin_user)

    assert client.get(reverse("admin:index")).status_code == 200


def test_anonymous_cannot_open_the_backoffice(client):
    assert is_redirect_to_login(client.get(reverse("admin:index")))


def test_coordination_cannot_open_the_backoffice(client, coordinator):
    login_verified(client, coordinator)

    assert is_redirect_to_login(client.get(reverse("admin:index")))
    assert is_redirect_to_login(client.get(reverse("admin:core_user_changelist")))


def test_deactivated_admin_cannot_open_the_backoffice(client, admin_user):
    login_verified(client, admin_user)
    User.objects.update(is_active=False)

    assert is_redirect_to_login(client.get(reverse("admin:index")))


def test_backoffice_login_sends_to_the_portal_login(client):
    response = client.get(reverse("admin:login") + "?next=/admin/")

    assert response.status_code == 302
    assert response.url == reverse("login") + "?next=/admin/"


def test_login_page_is_in_european_portuguese(client):
    page = client.get(reverse("login")).content.decode()

    assert "Endereço de e-mail" in page
    assert "Palavra-passe" in page
    assert "Senha" not in page


def test_admin_logs_in_and_must_set_up_two_factor_before_the_backoffice(client, admin_user):
    response = client.post(
        reverse("login"),
        {"username": "ADMIN@example.test", "password": "palavra-longa-e-rara"},
    )

    assert response.status_code == 302
    response = client.get(reverse("admin:index"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("two_factor_setup"))


def test_backoffice_refuses_the_admin_without_the_second_factor(client, admin_user):
    # Even if the middleware were left out, the site itself asks for a verified session.
    client.force_login(admin_user)

    request = RequestFactory().get("/admin/")
    request.user = admin_user
    admin_user.is_verified = lambda: False

    assert not admin.site.has_permission(request)


def test_password_is_not_on_the_user_page_and_cannot_be_posted(client, admin_user, make_user):
    person = make_user(password=PASSWORD)
    login_verified(client, admin_user)
    url = reverse("admin:core_user_change", args=[person.pk])

    assert 'name="password' not in client.get(url).content.decode()

    client.post(
        url,
        {
            "email": person.email,
            "full_name": person.full_name,
            "is_active": "on",
            "password": "definida-pelo-admin",
            "password1": "definida-pelo-admin",
            "password2": "definida-pelo-admin",
        },
    )
    person.refresh_from_db()
    assert person.check_password(PASSWORD)


def test_there_is_no_view_to_set_another_persons_password(client, admin_user, make_user):
    person = make_user(password=PASSWORD)
    login_verified(client, admin_user)

    with pytest.raises(NoReverseMatch):
        reverse("admin:auth_user_password_change", args=[person.pk])

    response = client.get(f"/admin/core/user/{person.pk}/password/", follow=True)

    assert 'name="password' not in response.content.decode()


def test_user_created_in_the_backoffice_has_no_usable_password(client, admin_user):
    login_verified(client, admin_user)

    response = client.post(
        reverse("admin:core_user_add"),
        {
            "email": "Nova@example.test",
            "full_name": "Nova",
            "is_active": "on",
            "password": "definida-pelo-admin",
        },
    )

    assert response.status_code == 302
    created = User.objects.get(email="nova@example.test")
    assert not created.has_usable_password()
    assert not created.is_superuser


def test_nobody_can_be_made_admin_in_the_backoffice(client, admin_user, make_user):
    person = make_user()
    login_verified(client, admin_user)

    client.post(
        reverse("admin:core_user_change", args=[person.pk]),
        {
            "email": person.email,
            "full_name": person.full_name,
            "is_active": "on",
            "is_superuser": "on",
        },
    )

    person.refresh_from_db()
    assert not person.is_superuser


def test_normal_account_can_be_deactivated_in_the_backoffice(client, admin_user, make_user):
    person = make_user()
    login_verified(client, admin_user)

    client.post(
        reverse("admin:core_user_change", args=[person.pk]),
        {"email": person.email, "full_name": person.full_name},
    )

    person.refresh_from_db()
    assert not person.is_active


def test_admin_cannot_be_deactivated_in_the_backoffice(client, admin_user):
    login_verified(client, admin_user)

    client.post(
        reverse("admin:core_user_change", args=[admin_user.pk]),
        {"email": admin_user.email, "full_name": admin_user.full_name},
    )

    admin_user.refresh_from_db()
    assert admin_user.is_active


def test_accounts_cannot_be_deleted_in_the_backoffice(client, admin_user, make_user):
    person = make_user()
    login_verified(client, admin_user)

    response = client.post(reverse("admin:core_user_delete", args=[person.pk]), {"post": "yes"})
    client.post(
        reverse("admin:core_user_changelist"),
        {"action": "delete_selected", "_selected_action": [person.pk], "post": "yes"},
    )

    assert response.status_code == 403
    assert User.objects.filter(pk=person.pk).exists()


def test_backoffice_rejects_an_invalid_membership(client, admin_user, make_user, location):
    person = make_user()
    login_verified(client, admin_user)

    response = client.post(
        reverse("admin:core_membership_add"),
        {
            "user": person.pk,
            "location": location.pk,
            "role": Role.PROFESSIONAL,
            "subrole": "",
            "start_date": "2026-01-01",
        },
    )

    assert response.status_code == 200
    assert not Membership.objects.exists()


def test_backoffice_saves_a_location(client, admin_user):
    login_verified(client, admin_user)

    response = client.post(
        reverse("admin:core_location_add"), {"name": "Polo C", "address": "", "is_active": "on"}
    )

    assert response.status_code == 302
    assert Location.objects.filter(name="Polo C").exists()


def test_django_groups_are_not_in_the_backoffice():
    assert not admin.site.is_registered(Group)
