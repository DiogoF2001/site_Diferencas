#!/bin/bash
# Checks the production setup against real containers, which pytest cannot do: a new database with
# the real init-roles.sh, the production image, and each user connecting over the network with its
# password. Uses its own Compose project and throwaway values, so it leaves any other stack alone.
set -euo pipefail

repo_root=$(cd "$(dirname "$0")/../.." && pwd)
# Inside the repository: not every Docker daemon can see the host's /tmp.
work=$(mktemp -d "$repo_root/deploy/.check-XXXXXX")
failures=0

compose() {
    docker compose -p diferencas-check --env-file "$work/.env" \
        -f "$repo_root/deploy/docker-compose.yml" --profile ops "$@"
}

cleanup() {
    compose down -v --remove-orphans >/dev/null 2>&1 || true
    rm -rf "$work"
}
trap cleanup EXIT

pass() { echo "ok    $1"; }
fail() {
    echo "FAIL  $1" >&2
    [ -z "${2:-}" ] || echo "      $2" >&2
    failures=$((failures + 1))
}

# Not to localhost, which the Postgres image trusts without a password.
psql_as() {
    local user=$1 password=$2 sql=$3
    compose exec -T -e PGPASSWORD="$password" db psql --host=db --username="$user" \
        --dbname="$POSTGRES_DB" --no-psqlrc --tuples-only --no-align \
        --set ON_ERROR_STOP=1 --command="$sql"
}

expect_allowed() {
    local label=$1 output
    if output=$(psql_as "$2" "$3" "$4" 2>&1); then pass "$label"; else fail "$label" "$output"; fi
}

expect_denied() {
    local label=$1 output
    if output=$(psql_as "$2" "$3" "$4" 2>&1); then
        fail "$label" "the command was allowed"
    elif grep -qE 'permission denied|must be owner' <<<"$output"; then
        pass "$label"
    else
        fail "$label" "failed for another reason: $output"
    fi
}

expect_equal() {
    local label=$1 expected=$2 actual=$3
    if [ "$expected" = "$actual" ]; then pass "$label"; else fail "$label" "got: $actual"; fi
}

echo "== Preparing a throwaway stack"
while IFS= read -r line; do
    case "$line" in
        DJANGO_SECRET_KEY=* | *_PASSWORD=*) echo "${line%%=*}=$(openssl rand -hex 32)" ;;
        *) echo "$line" ;;
    esac
done <"$repo_root/deploy/.env.example" >"$work/.env"
mkdir "$work/backups"
cat >>"$work/.env" <<ENV
BACKUP_DIR=$work/backups
BACKUP_UID=$(id -u)
BACKUP_GID=$(id -g)
ENV
# shellcheck disable=SC1091
source "$work/.env"

compose build app backup
compose run --rm --no-deps -T --entrypoint age-keygen backup >"$work/backups/age.key"
recipient=$(sed -n 's/^# public key: //p' "$work/backups/age.key")
echo "BACKUP_AGE_RECIPIENT=$recipient" >>"$work/.env"

compose up -d --wait app worker
compose run --rm migrate

echo "== Credentials"
config=$(compose config)
expect_equal "only db gets the superuser password" 1 "$(grep -c "$POSTGRES_PASSWORD" <<<"$config")"
expect_equal "only db and migrate get the owner password" 2 \
    "$(grep -c "$PORTAL_OWNER_PASSWORD" <<<"$config")"
expect_equal "only db and backup get the backup password" 2 \
    "$(grep -c "$PORTAL_BACKUP_PASSWORD" <<<"$config")"
expect_equal "only create-admin gets the admin password" 1 \
    "$(grep -c "$PORTAL_ADMIN_PASSWORD" <<<"$config")"
if psql_as "$PORTAL_DB_USER" wrong-password "SELECT 1" >/dev/null 2>&1; then
    fail "a wrong password is refused" "the connection was accepted"
else
    pass "a wrong password is refused"
fi

echo "== Table owner"
roles_sql="SELECT string_agg(rolsuper::text || rolcreaterole::text || rolcreatedb::text, ',')
    FROM pg_roles WHERE rolname IN ('$PORTAL_OWNER_USER', '$PORTAL_DB_USER', '$PORTAL_BACKUP_USER')"
expect_equal "owner, app and backup have no superuser, createrole or createdb" \
    "falsefalsefalse,falsefalsefalse,falsefalsefalse" \
    "$(psql_as "$PORTAL_OWNER_USER" "$PORTAL_OWNER_PASSWORD" "$roles_sql")"
expect_equal "the owner owns the tables created by migrate" \
    "$PORTAL_OWNER_USER" \
    "$(psql_as "$PORTAL_OWNER_USER" "$PORTAL_OWNER_PASSWORD" \
        "SELECT tableowner FROM pg_tables WHERE tablename = 'core_user'")"
expect_equal "migrate created btree_gist without being a superuser" 1 \
    "$(psql_as "$PORTAL_OWNER_USER" "$PORTAL_OWNER_PASSWORD" \
        "SELECT count(*) FROM pg_extension WHERE extname = 'btree_gist'")"
expect_allowed "owner can create and drop a table" "$PORTAL_OWNER_USER" "$PORTAL_OWNER_PASSWORD" \
    "BEGIN; CREATE TABLE check_owner (id int); DROP TABLE check_owner; ROLLBACK"
expect_denied "owner cannot create roles" "$PORTAL_OWNER_USER" "$PORTAL_OWNER_PASSWORD" \
    "CREATE ROLE check_role"
expect_denied "owner cannot create databases" "$PORTAL_OWNER_USER" "$PORTAL_OWNER_PASSWORD" \
    "CREATE DATABASE check_database"

echo "== App user"
app() { "$1" "$2" "$PORTAL_DB_USER" "$PORTAL_DB_PASSWORD" "$3"; }
app expect_allowed "app can read, insert, update and delete rows" \
    "BEGIN;
     INSERT INTO core_location (name, address, is_active) VALUES ('Polo', '', true);
     UPDATE core_location SET address = 'Rua';
     SELECT * FROM core_location;
     DELETE FROM core_location;
     ROLLBACK"
app expect_denied "app cannot create tables" "CREATE TABLE check_app (id int)"
app expect_denied "app cannot create temporary tables" "CREATE TEMP TABLE check_app (id int)"
app expect_denied "app cannot drop tables" "DROP TABLE core_location"
app expect_denied "app cannot alter tables" "ALTER TABLE core_location ADD COLUMN check_app int"
app expect_denied "app cannot truncate tables" "TRUNCATE core_location CASCADE"
app expect_denied "app cannot create schemas" "CREATE SCHEMA check_app"

echo "== Admin account"
if compose run --rm create-admin >/dev/null && compose run --rm create-admin >/dev/null; then
    pass "create-admin runs twice"
else
    fail "create-admin runs twice"
fi

echo "== Backup user"
backup() { "$1" "$2" "$PORTAL_BACKUP_USER" "$PORTAL_BACKUP_PASSWORD" "$3"; }
expect_equal "backup can read and create-admin left exactly one admin" 1 \
    "$(psql_as "$PORTAL_BACKUP_USER" "$PORTAL_BACKUP_PASSWORD" \
        "SELECT count(*) FROM core_user WHERE is_superuser")"
backup expect_denied "backup cannot insert" \
    "INSERT INTO core_location (name, address, is_active) VALUES ('Polo', '', true)"
backup expect_denied "backup cannot update" "UPDATE core_user SET full_name = 'x'"
backup expect_denied "backup cannot delete" "DELETE FROM core_user"
backup expect_denied "backup cannot truncate" "TRUNCATE core_location CASCADE"
backup expect_denied "backup cannot advance sequences" \
    "SELECT nextval(pg_get_serial_sequence('core_location', 'id'))"
backup expect_denied "backup cannot create tables" "CREATE TABLE check_backup (id int)"
backup expect_denied "backup cannot drop tables" "DROP TABLE core_location"

compose run --rm --no-deps -T backup once
# shellcheck disable=SC2016
if listing=$(compose run --rm --no-deps -T --entrypoint bash backup -c \
    'age --decrypt --identity /backups/age.key /backups/*.dump.age | pg_restore --list'); then
    if grep -q 'TABLE DATA public core_user' <<<"$listing"; then
        pass "the backup decrypts to a valid dump with the data"
    else
        fail "the backup decrypts to a valid dump with the data" "core_user is not in the dump"
    fi
else
    fail "the backup decrypts to a valid dump with the data" "$listing"
fi

echo "== Production image"
expect_equal "translations were compiled in the image" polo \
    "$(compose exec -T app python manage.py shell --verbosity 0 --command \
        'from core.models import Location; print(Location._meta.verbose_name)')"

if output=$(compose exec -T -e PORTAL_ADMIN_EMAIL="$PORTAL_ADMIN_EMAIL" \
    -e PORTAL_ADMIN_PASSWORD="$PORTAL_ADMIN_PASSWORD" app python - 2>&1 <<'PY'
import http.cookies
import os
import re
import urllib.error
import urllib.parse
import urllib.request

HOST = os.environ["DJANGO_ALLOWED_HOSTS"].split(",")[0]
cookies = http.cookies.SimpleCookie()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def fetch(path, data=None, **headers):
    """The way Caddy reaches the app, keeping the Secure cookies that plain HTTP would lose."""
    request = urllib.request.Request(
        f"http://127.0.0.1:8000{path}",
        data=urllib.parse.urlencode(data).encode() if data else None,
        headers={
            "Host": HOST,
            "X-Forwarded-Proto": "https",
            "Cookie": "; ".join(f"{key}={value.value}" for key, value in cookies.items()),
            **headers,
        },
    )
    try:
        response = urllib.request.build_opener(NoRedirect).open(request, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    for header in response.headers.get_all("Set-Cookie") or []:
        cookies.load(header)
    return response


login_page = fetch("/admin/login/")
assert login_page.status == 200, f"login page: {login_page.status}"
html = login_page.read().decode()

stylesheet = re.search(r'/static/admin/css/base\.[0-9a-f]{12}\.css', html)
assert stylesheet, "the login page does not link a hashed stylesheet"
css = fetch(stylesheet.group(0), **{"Accept-Encoding": "gzip"})
assert css.status == 200, f"stylesheet: {css.status}"
assert css.headers["Content-Type"].startswith("text/css"), css.headers["Content-Type"]
assert css.headers["Content-Encoding"] == "gzip", css.headers["Content-Encoding"]
assert "immutable" in css.headers["Cache-Control"], css.headers["Cache-Control"]
assert fetch("/static/admin/css/nao-existe.css").status == 404, "missing file"

token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)
login = fetch(
    "/admin/login/",
    {
        "csrfmiddlewaretoken": token,
        "username": os.environ["PORTAL_ADMIN_EMAIL"],
        "password": os.environ["PORTAL_ADMIN_PASSWORD"],
        "next": "/admin/",
    },
    Referer=f"https://{HOST}/admin/login/",
)
assert login.status == 302, f"login: {login.status}"
assert fetch("/admin/").status == 200, "backoffice after login"
PY
); then
    pass "WhiteNoise serves the backoffice's hashed, compressed static files"
    pass "the admin logs in to the backoffice, using the app's database user"
else
    fail "WhiteNoise and the backoffice login" "$output"
fi

echo
if [ "$failures" -gt 0 ]; then
    echo "$failures check(s) failed" >&2
    exit 1
fi
echo "All checks passed"
