#!/bin/sh
# Runs in the "backup" container: a database backup now, then one every 24 hours.
# Backups land in ./backups on the server; the newest 14 are kept.
set -eu

while true; do
    file="/backups/share_market-$(date +%Y-%m-%d_%H%M).dump"
    if pg_dump -h postgres -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$file.tmp"; then
        mv "$file.tmp" "$file"
        echo "Backup saved: $file"
    else
        rm -f "$file.tmp"
        echo "Backup FAILED" >&2
    fi
    ls -1t /backups/*.dump 2>/dev/null | tail -n +15 | xargs -r rm -f
    sleep 86400
done
