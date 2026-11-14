#!/usr/bin/env bash
# Run as the unprivileged timmy-deploy user.
set -Eeuo pipefail
umask 022

if [[ $# -lt 1 || $# -gt 2 || ! "$1" =~ ^[0-9a-f]{40}$ ]]; then
  echo 'Usage: stage-release.sh <40-character-main-SHA> [--stage-only]' >&2
  exit 2
fi
sha="$1"
mode="deploy"
if [[ $# -eq 2 ]]; then
  [[ "$2" == '--stage-only' ]] || exit 2
  mode="stage-only"
fi

root=/srv/timmy
repo="$HOME/timmy-source.git"
release="$root/releases/$sha"
key="$HOME/.ssh/github_readonly"
[[ -r "$key" ]] || { echo 'Missing read-only GitHub deploy key' >&2; exit 1; }
[[ -d "$root/releases" ]] || { echo 'Server not bootstrapped: /srv/timmy/releases missing' >&2; exit 1; }
command -v flock >/dev/null
command -v node >/dev/null
command -v npm >/dev/null
command -v python3 >/dev/null
node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 22 ? 0 : 1)'

# Serialize preparation and activation.
exec 9>"$HOME/.timmy-deploy.lock"
flock -w 900 9
export GIT_SSH_COMMAND="ssh -i $key -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o BatchMode=yes -o UserKnownHostsFile=$HOME/.ssh/known_hosts"
if [[ ! -d "$repo" ]]; then
  git init --bare "$repo"
  git --git-dir="$repo" remote add origin git@github.com:charbel0004/Timmy.git
fi
git --git-dir="$repo" fetch --no-tags --prune origin '+refs/heads/main:refs/remotes/origin/main'
head="$(git --git-dir="$repo" rev-parse refs/remotes/origin/main)"
if [[ "$head" != "$sha" ]]; then
  echo "Superseded: requested $sha, current main $head; not deploying an older commit."
  exit 0
fi

if [[ -e "$release" && ! -f "$release/.timmy-ready" ]]; then
  echo "Incomplete release $release; requires operator cleanup" >&2
  exit 1
fi

if [[ ! -f "$release/.timmy-ready" ]]; then
  mkdir "$release"
  git --git-dir="$repo" archive "$sha" | tar -x -C "$release"
  cd "$release"
  python3 -m venv .venv
  .venv/bin/python -m pip install -r backend/requirements-dev.txt

  # Never use the operational database or secrets in release tests.
  export PYTHONPATH=backend
  export TIMMY_DATABASE_URL="sqlite:///$release/.timmy-stage.db"
  export TIMMY_DOCUMENT_ROOT="$release/.test-documents"
  export TIMMY_WEEKLY_ENABLED=false
  export TIMMY_DEMO_MODE=false
  .venv/bin/python -m pytest -q backend/tests -p no:cacheprovider
  rm -f .timmy-stage.db .timmy-stage.db-wal .timmy-stage.db-shm
  .venv/bin/alembic -c backend/alembic.ini upgrade head
  revision="$(sqlite3 .timmy-stage.db 'SELECT version_num FROM alembic_version LIMIT 1')"
  [[ -n "$revision" ]] || { echo 'Missing Alembic revision' >&2; exit 1; }
  [[ "$(sqlite3 .timmy-stage.db 'PRAGMA integrity_check')" == 'ok' ]]
  printf '%s\n' "$revision" > .timmy-schema-revision

  npm ci --prefix frontend
  npm test --prefix frontend
  VITE_API_URL=/api npm run build --prefix frontend
  test -s frontend/dist/index.html
  test -d frontend/dist/assets

  rm -rf frontend/node_modules .timmy-stage.db .timmy-stage.db-wal \
    .timmy-stage.db-shm .test-documents logs .pytest_cache
  ln -s "$root/shared/.env" .env
  ln -s "$root/shared/timmy.db" timmy.db
  ln -s "$root/shared/logs" logs
  # document_root is configured as an absolute path in shared/.env.
  touch .timmy-ready
fi

if [[ "$mode" == 'stage-only' ]]; then
  echo "Staged and verified $sha at $release. Activation not requested."
else
  sudo -n /usr/local/sbin/timmy-activate-release "$sha"
fi
