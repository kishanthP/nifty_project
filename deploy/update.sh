#!/usr/bin/env bash
# Run on the server, in the project folder, after you push new code to GitHub:
#     bash deploy/update.sh
#
# Gets the latest code, rebuilds what changed and restarts it. The database,
# HTTPS certificates and backups are kept.
set -euo pipefail
cd "$(dirname "$0")/.."

git pull --ff-only
docker compose -f docker-compose.prod.yml up -d --build --remove-orphans
docker image prune -f >/dev/null
docker compose -f docker-compose.prod.yml ps
