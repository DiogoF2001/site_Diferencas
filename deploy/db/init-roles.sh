#!/bin/bash
# Runs once, when the data directory is created, and is the only use of POSTGRES_USER (superuser).
# PORTAL_OWNER_USER owns the tables and runs the migrations. PORTAL_DB_USER is what the app and
# worker connect with, and owns nothing, so the append-only rules on the history tables cannot be
# undone from the application. PORTAL_BACKUP_USER can only read.
set -euo pipefail

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set ON_ERROR_STOP=1 \
    --set db_name="$POSTGRES_DB" \
    --set owner_user="$PORTAL_OWNER_USER" \
    --set owner_password="$PORTAL_OWNER_PASSWORD" \
    --set app_user="$PORTAL_DB_USER" \
    --set app_password="$PORTAL_DB_PASSWORD" \
    --set backup_user="$PORTAL_BACKUP_USER" \
    --set backup_password="$PORTAL_BACKUP_PASSWORD" <<'SQL'
CREATE ROLE :"owner_user" LOGIN PASSWORD :'owner_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE :"backup_user" LOGIN PASSWORD :'backup_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;

-- Owning the database lets the owner create tables in the public schema and trusted extensions
-- such as btree_gist.
ALTER DATABASE :"db_name" OWNER TO :"owner_user";
-- By default everyone could connect and create temporary tables.
REVOKE ALL ON DATABASE :"db_name" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db_name" TO :"app_user", :"backup_user";

GRANT USAGE ON SCHEMA public TO :"app_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_user" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_user" IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO :"app_user";

GRANT pg_read_all_data TO :"backup_user";
SQL
