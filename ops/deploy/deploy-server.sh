#!/usr/bin/env bash
# Hackathon MVP: update ONE checkout in place, test, build, then restart.
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

mkdir -p -m 700 "$backups"
stamp="$(date -u +%Y%m%d-%H%M%S)"
sqlite3 timmy.db ".backup '$backups/timmy-$stamp.db'"
[[ "$(sqlite3 "$backups/timmy-$stamp.db" 'PRAGMA quick_check')" == ok ]] || exit 1

# Temporary test data and static-file rollback copy, NOT a release directory.
temp="$(mktemp -d /tmp/timmy-deploy.XXXXXXXX)"
rsync -a "$web/" "$temp/previous-web/"

needs_restore=false
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
    if [[ "$web_changed" == true ]]; then
      rsync -a --delete "$temp/previous-web/" "$web/"
    fi
    systemctl start timmy-api
    curl -fsS --max-time 5 http://127.0.0.1:8000/api/health || true
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
git reset --hard "$requested"

"$uv" pip install --python .venv/bin/python -r backend/requirements-dev.txt

# Tests and migrations use a disposable SQLite database, never timmy.db.
export TIMMY_DATABASE_URL="sqlite:///$temp/test.db"
export TIMMY_DOCUMENT_ROOT="$temp/documents"
export TIMMY_WEEKLY_ENABLED=false
export TIMMY_DEMO_MODE=false
export PYTHONPATH=backend
.venv/bin/python -m pytest -q backend/tests -p no:cacheprovider --basetemp="$temp/pytest"
.venv/bin/alembic -c backend/alembic.ini upgrade head
[[ "$(sqlite3 "$temp/test.db" 'PRAGMA integrity_check')" == ok ]]
unset TIMMY_DATABASE_URL TIMMY_DOCUMENT_ROOT TIMMY_WEEKLY_ENABLED TIMMY_DEMO_MODE PYTHONPATH

# Any schema upgrade must be performed separately and reviewed; rollback is code-only.
live_revision="$(sqlite3 timmy.db 'SELECT version_num FROM alembic_version LIMIT 1')"
desired_revision="$(.venv/bin/alembic -c backend/alembic.ini heads | awk 'NR==1 {print $1}')"
[[ -n "$desired_revision" && "$live_revision" == "$desired_revision" ]] || {
  echo "Migration gate: live=$live_revision expected=$desired_revision" >&2
  exit 1
}

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
