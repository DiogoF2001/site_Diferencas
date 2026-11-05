#!/bin/bash
# Daily encrypted pg_dump. Only the age public key is on the server, so these files cannot be
# read from it. `backup.sh once` takes a single backup and exits.
set -uo pipefail

: "${PGDATABASE:?}" "${BACKUP_AGE_RECIPIENT:?}" "${BACKUP_TIME:?}" "${BACKUP_RETENTION_DAYS:?}"

BACKUP_DIR=/backups
FAILED_MARKER=/tmp/backup-failed

log() {
    echo "$(date --iso-8601=seconds) $*"
}

run_backup() {
    local target
    target="$BACKUP_DIR/$PGDATABASE-$(date -u +%Y%m%dT%H%M%SZ).dump.age"

    umask 077
    if ! pg_dump --format=custom | age --recipient "$BACKUP_AGE_RECIPIENT" --output "$target.partial"; then
        rm -f "$target.partial"
        return 1
    fi
    mv "$target.partial" "$target" || return 1
    log "Backup written: $target"

    # Only after a successful backup, so failures never eat into the existing copies.
    find "$BACKUP_DIR" -maxdepth 1 -name '*.dump.age' -mtime +"$BACKUP_RETENTION_DAYS" -delete
}

seconds_until_next_run() {
    local now next
    now=$(date +%s)
    next=$(date -d "today $BACKUP_TIME" +%s 2>/dev/null) || next=0
    if [ "$next" -le "$now" ]; then
        # A time inside a daylight saving gap does not exist: try again in an hour.
        next=$(date -d "tomorrow $BACKUP_TIME" +%s 2>/dev/null) || next=$((now + 3600))
    fi
    echo $((next - now))
}

if [ ! -w "$BACKUP_DIR" ]; then
    log "ERROR: $BACKUP_DIR is not writable; check BACKUP_UID and BACKUP_GID" >&2
    exit 1
fi

if [ "${1:-}" = "once" ]; then
    run_backup
    exit
fi

trap 'exit 0' TERM INT
log "Backup service started; next run at $BACKUP_TIME ($TZ)"
while true; do
    sleep "$(seconds_until_next_run)" &
    wait $!
    if run_backup; then
        rm -f "$FAILED_MARKER"
    else
        log "ERROR: backup failed" >&2
        touch "$FAILED_MARKER"
    fi
done
