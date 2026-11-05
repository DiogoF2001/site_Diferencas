#!/bin/bash
# Runs once, when the data directory is created. POSTGRES_USER owns the tables and runs the
# migrations; PORTAL_DB_USER is what the app and worker connect with, and owns nothing, so the
# append-only rules on the history tables cannot be undone from the application.
set -euo pipefail

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set ON_ERROR_STOP=1 \
    --set app_user="$PORTAL_DB_USER" \
    --set app_password="$PORTAL_DB_PASSWORD" <<'SQL'
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
GRANT USAGE ON SCHEMA public TO :"app_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO :"app_user";
SQL
