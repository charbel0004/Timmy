#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/alembic -c backend/alembic.ini upgrade head
exec .venv/bin/uvicorn timmy.main:app --app-dir backend --host localhost --port 8000
