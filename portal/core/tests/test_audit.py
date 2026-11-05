import importlib

import pytest
from django.db import connection, migrations
from django.db.migrations.state import ProjectState

from core.audit import Action, record
from core.db import revoke_changes
from core.models import AuditEvent

pytestmark = pytest.mark.django_db

ROLE = "check_audit_app_role"


def test_event_is_recorded(make_user, location):
    person = make_user()

    event = record(Action.ACCOUNT_DEACTIVATED, target=person, location=location, reason="saída")

    assert AuditEvent.objects.get() == event
    assert event.details == {"reason": "saída"}
    assert event.actor is None


def test_saved_event_cannot_be_changed(make_user):
    event = record(Action.LOGIN_FAILED, email="x@example.test")
    event.email = "y@example.test"

    with pytest.raises(TypeError):
        event.save()


def test_event_cannot_be_deleted():
    event = record(Action.LOGIN_FAILED, email="x@example.test")

    with pytest.raises(TypeError):
        event.delete()
    with pytest.raises(TypeError):
        AuditEvent.objects.all().delete()
    with pytest.raises(TypeError):
        AuditEvent.objects.update(email="")

    assert AuditEvent.objects.filter(pk=event.pk).exists()


def test_revoke_changes_refuses_what_is_not_a_table_name():
    with pytest.raises(ValueError):
        revoke_changes("core_auditevent; DROP TABLE core_user")


@pytest.fixture
def app_role():
    """A role with the privileges the production app user gets by default (init-roles.sh)."""
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE ROLE {ROLE}")
        cursor.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON core_auditevent TO {ROLE}"
        )
        cursor.execute(f"GRANT SELECT, UPDATE ON core_location TO {ROLE}")
    yield ROLE
    with connection.cursor() as cursor:
        cursor.execute(f"DROP OWNED BY {ROLE}")
        cursor.execute(f"DROP ROLE {ROLE}")


def privileges(role, table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT p FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE']) p"
            " WHERE has_table_privilege(%s, %s, p)",
            [role, table],
        )
        return {row[0] for row in cursor.fetchall()}


def test_migration_leaves_the_audit_table_append_only_for_the_app_role(app_role):
    operation = revoke_changes("core_auditevent")
    with connection.schema_editor() as editor:
        operation.database_forwards("core", editor, ProjectState(), ProjectState())

    assert privileges(app_role, "core_auditevent") == {"SELECT", "INSERT"}
    # Other tables keep what they had.
    assert privileges(app_role, "core_location") == {"SELECT", "UPDATE"}


def test_the_audit_migration_revokes_changes():
    module = importlib.import_module("core.migrations.0002_audit_event")
    operations = [
        operation
        for operation in module.Migration.operations
        if isinstance(operation, migrations.RunSQL)
    ]

    assert [operation.sql for operation in operations] == [revoke_changes("core_auditevent").sql]
