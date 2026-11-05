"""Database-level rules that Django cannot express in a model."""

from django.db import migrations


def revoke_changes(table):
    """Migration operation that leaves `table` append-only for every role but its owner.

    It runs as the owner (the `migrate` service), so it removes UPDATE, DELETE and TRUNCATE from
    the roles the owner granted them to, such as the app's database user. Where nobody else has
    them, as in development and the tests, it changes nothing.
    """
    if not table.isidentifier():
        raise ValueError(f"Not a table name: {table!r}")
    # The table name comes from the migration's code, never from input.
    return migrations.RunSQL(
        sql=f"""
        DO $$
        DECLARE grantee_name text;
        BEGIN
            FOR grantee_name IN
                SELECT DISTINCT grantee FROM information_schema.role_table_grants
                WHERE table_schema = current_schema()
                    AND table_name = '{table}'
                    AND privilege_type IN ('UPDATE', 'DELETE', 'TRUNCATE')
                    AND grantee <> current_user
            LOOP
                EXECUTE format(
                    'REVOKE UPDATE, DELETE, TRUNCATE ON %I FROM %I', '{table}', grantee_name
                );
            END LOOP;
        END
        $$;
        """,  # noqa: S608
        reverse_sql=migrations.RunSQL.noop,
    )
