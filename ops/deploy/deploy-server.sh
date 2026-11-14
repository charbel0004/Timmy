#!/usr/bin/env bash
# Hackathon MVP: guarded one-checkout deploy, isolated tests, specific schema upgrade.
# Installed as root-owned /usr/local/sbin/timmy-deploy.
set -Eeuo pipefail
umask 077

if [[ $EUID -ne 0 || $# -ne 1 || ! "$1" =~ ^[0-9a-f]{40}$ ]]; then
  echo 'Usage (root): timmy-deploy <40-character main SHA>' >&2
  exit 2
fi

requested="$1"
repo=/root/apps/Timmy
web=/var/www/timmy
backups=/root/timmy-backups
uv=/root/.local/bin/uv
isolated_checks="$repo/ops/deploy/run-isolated-backend-checks.sh"

cd "$repo"
exec 9>/run/lock/timmy-deploy.lock
flock -w 600 9

[[ -x "$uv" && -x .venv/bin/python && -f .env && -f timmy.db ]] || {
  echo 'Missing existing Python environment, config, or database' >&2; exit 1;
}
[[ -d "$web" ]] || { echo 'Missing Nginx static web root' >&2; exit 1; }

# Refuse a running backend outside systemd. The first cutover is manual.
service_pid="$(systemctl show -p MainPID --value timmy-api)"
if ! systemctl is-active --quiet timmy-api || [[ "$service_pid" == 0 ]] ||
   ! ss -ltnp '( sport = :8000 )' | grep -q "pid=$service_pid,"; then
  echo 'timmy-api must own port 8000 before automated deployments' >&2
  exit 1
fi

# Origin/main must be exactly the SHA that passed the GitHub CI workflow.
git fetch --no-tags origin main
head="$(git rev-parse FETCH_HEAD)"
[[ "$head" == "$requested" ]] || {
  echo "Superseded or unexpected commit: $requested (main is $head)" >&2; exit 1;
}
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || {
  echo 'Tracked checkout files have local changes; refusing to overwrite' >&2; exit 1;
}
previous="$(git rev-parse HEAD)"
if [[ "$previous" == "$requested" ]]; then
  echo "Already deployed $requested"
  exit 0
fi

# Temporary test data and static-file rollback copy, NOT a release directory.
temp="$(mktemp -d /tmp/timmy-deploy.XXXXXXXX)"
rsync -a "$web/" "$temp/previous-web/"

mkdir -p -m 700 "$backups"
stamp="$(date -u +%Y%m%d-%H%M%S)"
backup_file="$backups/timmy-$stamp.db"
original_revision="$(sqlite3 timmy.db 'SELECT version_num FROM alembic_version LIMIT 1')"

needs_restore=false
migration_attempted=false
web_changed=false
cleanup() {
  code="$?"
  trap - EXIT
  set +e
  if [[ "$code" != 0 && "$needs_restore" == true ]]; then
    echo 'Deployment failed: restoring prior checkout and restarting backend' >&2
    cd "$repo" || exit "$code"
    git reset --hard "$previous"
    "$uv" pip install --python .venv/bin/python -r backend/requirements-dev.txt

    # Forward-only migrations require restoration of the consistent offline
    # backup if ANY later release gate fails. Never restart old code on 0017.
    recovery_ok=true
    if [[ "$migration_attempted" == true ]]; then
      if ! sqlite3 timmy.db ".restore '$backup_file'" ||
         [[ "$(sqlite3 timmy.db 'PRAGMA integrity_check')" != ok ]] ||
         [[ "$(sqlite3 timmy.db 'SELECT version_num FROM alembic_version LIMIT 1')" != "$original_revision" ]]; then
        recovery_ok=false
        echo "DATABASE_RESTORE_FAILED: leave service stopped; inspect $backup_file" >&2
      fi
    fi
    if [[ "$web_changed" == true ]]; then
      rsync -a --delete "$temp/previous-web/" "$web/"
    fi
    if [[ "$recovery_ok" == true ]]; then
      systemctl start timmy-api
      recovered=false
      for i in {1..25}; do
        if curl -fsS --max-time 2 http://127.0.0.1:8000/api/health 2>/dev/null |
             grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'; then
          recovered=true
          break
        fi
        sleep 2
      done
      [[ "$recovered" == true ]] ||
        echo 'ROLLBACK_HEALTH_FAILED: operator must check timmy-api service' >&2
    fi
  fi
  [[ -n "$temp" ]] && rm -rf -- "$temp"
  exit "$code"
}
trap cleanup EXIT

export NVM_DIR=/root/.nvm
if [[ -s "$NVM_DIR/nvm.sh" ]]; then
  # Node 22 installed via nvm in the original root checkout.
  source "$NVM_DIR/nvm.sh"
  nvm use 22 >/dev/null
fi
node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 22 ? 0 : 1)'
command -v npm >/dev/null

needs_restore=true
systemctl stop timmy-api

# Take an OFFLINE, consistent snapshot after stopping the only API writer.
# Never use the pre-stop backup for rollback: it can miss in-flight writes.
sqlite3 timmy.db ".backup '$backup_file'"
[[ "$(sqlite3 "$backup_file" 'PRAGMA integrity_check')" == ok ]] || exit 1
[[ -z "$(sqlite3 "$backup_file" 'PRAGMA foreign_key_check')" ]] || exit 1
[[ "$(sqlite3 "$backup_file" 'SELECT version_num FROM alembic_version LIMIT 1')" == "$original_revision" ]] || exit 1

git reset --hard "$requested"

"$uv" pip install --python .venv/bin/python -r backend/requirements-dev.txt

# Production .env MUST NOT leak into tests. The helper copies only backend
# source to a temporary root and runs tests with env -i on a disposable DB.
[[ -f "$isolated_checks" ]] || {
  echo 'Missing isolated test runner in requested commit' >&2; exit 1;
}
bash "$isolated_checks" "$repo" "$repo/.venv/bin/python" "$temp"

# This one-time release has an explicitly reviewed ADDITIVE migration.
# No unknown future migrations are permitted by unattended CD.
live_revision="$(sqlite3 timmy.db 'SELECT version_num FROM alembic_version LIMIT 1')"
desired_revision="$(.venv/bin/python -m alembic -c backend/alembic.ini heads | awk 'NR==1 {print $1}')"
if [[ "$live_revision" != "$desired_revision" ]]; then
  if [[ "$live_revision" != 0016 || "$desired_revision" != 0017 ]]; then
    echo "SCHEMA_CHANGE_NOT_APPROVED: live=$live_revision expected=$desired_revision" >&2
    exit 1
  fi
  echo 'APPLYING_APPROVED_SCHEMA_MIGRATION 0016 -> 0017'
  migration_attempted=true
  # Explicit database URL overrides the application's .env. The API is stopped.
  TIMMY_DATABASE_URL="sqlite:///$repo/timmy.db" PYTHONPATH="$repo/backend"     .venv/bin/python -m alembic -c backend/alembic.ini upgrade 0017
  [[ "$(sqlite3 timmy.db 'SELECT version_num FROM alembic_version LIMIT 1')" == 0017 ]]
  [[ "$(sqlite3 timmy.db 'PRAGMA integrity_check')" == ok ]]
  [[ -z "$(sqlite3 timmy.db 'PRAGMA foreign_key_check')" ]]
  echo 'APPROVED_SCHEMA_MIGRATION_VERIFIED'
fi

npm ci --prefix frontend
npm test --prefix frontend
VITE_API_URL=/api npm run build --prefix frontend
[[ -s frontend/dist/index.html && -d frontend/dist/assets ]]

web_changed=true
rsync -a --delete frontend/dist/ "$web/"
systemctl start timmy-api

healthy=false
for i in {1..25}; do
  if curl -fsS --max-time 2 http://127.0.0.1:8000/api/health 2>/dev/null |
       grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'; then
    healthy=true
    break
  fi
  sleep 2
done
[[ "$healthy" == true ]] || { echo 'Backend health check failed' >&2; exit 1; }
needs_restore=false
printf '%s\n' "$requested" > "$repo/.timmy-deployed-sha"
echo "DEPLOYED $requested"
