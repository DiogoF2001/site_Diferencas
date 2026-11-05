from unittest import mock

import pytest
from django.db import OperationalError
from django.test import Client, override_settings
from django.urls import reverse


@pytest.mark.django_db
def test_healthz_reports_ok_when_database_answers(client):
    response = client.get(reverse("healthz"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_reports_unavailable_without_details_when_database_fails(client):
    with mock.patch("core.views.connection") as connection:
        connection.cursor.side_effect = OperationalError("secret-host refused")
        response = client.get(reverse("healthz"))

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_healthz_rejects_writes(client):
    assert client.post(reverse("healthz")).status_code == 405


@pytest.mark.django_db
def test_healthz_is_exempt_from_https_redirect_but_other_paths_are_not():
    with override_settings(SECURE_SSL_REDIRECT=True):
        client = Client()

        assert client.get(reverse("healthz")).status_code == 200
        assert client.get("/other/").status_code == 301
