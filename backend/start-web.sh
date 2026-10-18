#!/bin/sh
# Default start command of the backend image (used as-is by Render).
# docker-compose files set their own commands and don't use this.
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
    --proxy-headers --forwarded-allow-ips="*"
