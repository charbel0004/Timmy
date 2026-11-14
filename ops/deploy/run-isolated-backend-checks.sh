#!/usr/bin/env bash
# Run backend tests and disposable migrations without reading production .env.
# Usage: run-isolated-backend-checks.sh REPO PYTHON SCRATCH [PYTEST_TARGET]
set -Eeuo pipefail
umask 077

if [[ $# -lt 3 || $# -gt 4 ]]; then
  echo 'Usage: run-isolated-backend-checks.sh REPO PYTHON SCRATCH [PYTEST_TARGET]' >&2
  exit 2
fi
repo="$1"
python="$2"
scratch="$3"
target="${4:-backend/tests}"
[[ -d "$repo/backend" && -x "$python" && -d "$scratch" ]] || {
  echo 'Isolated backend test prerequisites missing' >&2; exit 2;
}
[[ "$target" == backend/tests* ]] || {
  echo 'Test target must remain inside backend/tests' >&2; exit 2;
}

# Settings.env_file is calculated from the Python source location.
# Test against an isolated SOURCE ROOT, not against the live checkout that
# contains production .env (which may set HTTPS cookies, origin and AI config).
mkdir -p -m 700 "$scratch/source" "$scratch/home"
cp -a "$repo/backend" "$scratch/source/backend"
# Some backend regression tests assert deployment policy from ops/deploy.
# Bring only reviewed script/test fixtures, never root .env or live files.
mkdir -p "$scratch/source/ops"
cp -a "$repo/ops/deploy" "$scratch/source/ops/deploy"
# Deployment policy tests also verify the committed CI/CD workflow.
mkdir -p "$scratch/source/.github"
cp -a "$repo/.github/workflows" "$scratch/source/.github/workflows"
[[ ! -e "$scratch/source/.env" ]] || {
  echo 'Isolated source unexpectedly contains a .env file' >&2; exit 1;
}
cd "$scratch/source"

run_test_command() {
  env -i PATH=/usr/bin:/bin HOME="$scratch/home" LANG=C.UTF-8     PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$scratch/source/backend"     TIMMY_DATABASE_URL="sqlite:///$scratch/test.db"     TIMMY_DOCUMENT_ROOT="$scratch/documents"     TIMMY_WEEKLY_ENABLED=false TIMMY_DEMO_MODE=false     "$python" "$@"
}

run_test_command -m pytest -q "$target" -p no:cacheprovider --basetemp="$scratch/pytest"
run_test_command -m alembic -c "$scratch/source/backend/alembic.ini" upgrade head
run_test_command -m alembic -c "$scratch/source/backend/alembic.ini" current

# Validate the disposable copy, not the production database.
run_test_command -c 'import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []' "$scratch/test.db"
echo 'ISOLATED_BACKEND_CHECKS_PASSED'
