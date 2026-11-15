#!/usr/bin/env bash
# Install as root-owned /usr/local/sbin/timmy-deploy.
set -Eeuo pipefail
umask 027

die() { echo "$*" >&2; exit 1; }
[[ $EUID == 0 && $# == 1 ]] || die 'Run as root with an exact commit SHA or --bridge or --rollback'
requested=$1
[[ $requested == --rollback || $requested == --bridge || $requested =~ ^[0-9a-f]{40}$ ]] || die 'Invalid release identifier'

base=/opt/timmy-deploy
config=/etc/timmy/deploy.conf
[[ -f $config ]] || die 'Complete the production preflight before installing the deployer'
# Root-owned operator configuration, never sourced from a release.
source "$config"
: "${REPOSITORY:?}" "${DATABASE:?}" "${PUBLIC_ORIGIN:?}" "${NGINX_INCLUDE:?}" "${LEGACY_UNIT:?}" "${LEGACY_WEB:?}" "${LEGACY_SHA:?}" "${BUILD_PATH:?}"
exec 9>/run/lock/timmy-deploy.lock
flock -w 600 9
cd "$base"

health() {
  curl -fsS --max-time 3 "$1/api/health" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'
}

wait_health() {
  for attempt in {1..30}; do
    if health "$1"; then return; fi
    sleep 2
  done
  return 1
}

switch_link() {
  ln -sfn "$1" "$2.next"
  mv -Tf "$2.next" "$2"
}

write_route() {
  local web=$1 port=$2 sha=$3
  {
    printf '# %s %s\n' "$port" "$sha"
    printf 'set $timmy_backend http://127.0.0.1:%s;\n' "$port"
    printf 'root %s;\n' "$web"
  } > "$NGINX_INCLUDE.next"
  mv -Tf "$NGINX_INCLUDE.next" "$NGINX_INCLUDE"
}

read -r marker active active_sha < "$NGINX_INCLUDE"
[[ $marker == '#' && $active =~ ^800[01]$ && $active_sha =~ ^[0-9a-f]{40}$ ]] || die 'Invalid active routing metadata'
health "http://127.0.0.1:$active" || die 'Active backend is unhealthy'
[[ $(sqlite3 -readonly "$DATABASE" 'SELECT version_num FROM alembic_version') =~ ^[a-zA-Z0-9_]+$ ]] ||
  die 'Cannot establish production schema revision'
if [[ $active_sha == "$requested" && -L $base/current ]]; then
  echo "Already deployed $requested"
  exit 0
fi

slot=$((16001 - active))
unit="timmy-api@$slot.service"
active_unit="timmy-api@$active.service"
if [[ ! -L $base/current ]]; then
  [[ $active == 8000 && $active_sha == "$LEGACY_SHA" ]] || die 'Legacy routing differs from the inspected baseline'
  active_unit=$LEGACY_UNIT
else
  [[ $(readlink "$base/current") == "$base/releases/$active_sha" ]] ||
    die 'Current release differs from the active Nginx route'
fi
systemctl is-active --quiet "$active_unit" || die "Expected active unit $active_unit"
if systemctl is-active --quiet "$unit" || [[ -n $(ss -Hlt "( sport = :$slot )") ]]; then
  die "Standby port $slot is occupied or still draining"
fi

rollback=false
bridge=false
if [[ $requested == --bridge ]]; then
  [[ ! -L $base/current ]] || die 'Bridge is only for the initial cutover'
  bridge=true
  requested=$LEGACY_SHA
elif [[ $requested == --rollback ]]; then
  rollback=true
  requested=$(basename "$(readlink -e "$base/previous")")
  [[ $requested =~ ^[0-9a-f]{40}$ && $requested != "$active_sha" ]] || die 'No retained release to roll back to'
else
  git -C "$REPOSITORY" fetch --no-tags origin main
  [[ $(git -C "$REPOSITORY" rev-parse FETCH_HEAD) == "$requested" ]] || die 'Commit is no longer origin/main'
fi
echo "Active: $active_sha on $active; candidate: $requested on $slot"

# Admit only a declared, blob-pinned additive migration over a compatible release.
migrations() { git -C "$REPOSITORY" rev-parse "$1:backend/migrations"; }
migrate=false
compatible_rollback=false
reviewed_transition() {
  local older=$1 newer=$2
  local manifest=ops/deploy/additive-migration
  local declaration migration blob extra
  declaration=$(git -C "$REPOSITORY" show "$newer:$manifest" 2>/dev/null) || return 1
  [[ $declaration != *$'\n'* ]] || return 1
  read -r from_revision to_revision migration blob extra <<< "$declaration" || return 1
  [[ -z $extra && $from_revision =~ ^[a-zA-Z0-9_]+$ && $to_revision =~ ^[a-zA-Z0-9_]+$ &&
     $from_revision != "$to_revision" && $migration =~ ^backend/migrations/versions/[a-zA-Z0-9_]+\.py$ &&
     $blob =~ ^[0-9a-f]{40}$ &&
     $(git -C "$REPOSITORY" diff --name-status "$older" "$newer" -- backend/migrations) == $'A\t'"$migration" &&
     $(git -C "$REPOSITORY" rev-parse "$newer:$migration") == "$blob" ]] || return 1
  [[ -f $base/releases/$older/.additive-schema-compatible &&
     -O $base/releases/$older/.additive-schema-compatible ]] ||
    git -C "$REPOSITORY" cat-file -e "$older:$manifest"
}
if [[ $(migrations "$active_sha") != "$(migrations "$requested")" ]]; then
  if $rollback && [[ -f $base/releases/$requested/.schema-bridge ]]; then
    echo 'Rollback to bridge supports revision 0017'
  elif $rollback && reviewed_transition "$requested" "$active_sha"; then
    compatible_rollback=true
  elif ! $rollback && reviewed_transition "$active_sha" "$requested"; then
    migrate=true
  else
    migration=backend/migrations/versions/0017_workflow_step_receipts.py
    [[ -f $base/releases/$active_sha/.schema-bridge &&
       $(git -C "$REPOSITORY" diff --name-status "$active_sha" "$requested" -- backend/migrations) == $'A\t'"$migration" &&
       $(git -C "$REPOSITORY" rev-parse "$requested:$migration") == aea0fbd39b71978cac927a4ec859ec817332ab48 ]] ||
      die 'Migration tree changed; requires compatibility review'
    from_revision=0016
    to_revision=0017
    migrate=true
  fi
fi
release="$base/releases/$requested"
stage=
candidate_started=false
route_changed=false
route_backup=$(mktemp /etc/timmy/route.XXXXXXXX)
cp "$NGINX_INCLUDE" "$route_backup"
cleanup() {
  local code=$?
  trap - EXIT
  set +e
  if (( code != 0 )); then
    if $route_changed; then
      if health "http://127.0.0.1:$active" && cp "$route_backup" "$NGINX_INCLUDE.next" &&
           mv -Tf "$NGINX_INCLUDE.next" "$NGINX_INCLUDE" && nginx -t && systemctl reload nginx &&
           wait_health "$PUBLIC_ORIGIN"; then
        echo "Restored traffic to $active_sha; candidate retained for draining" >&2
      else
        echo "Routing rollback failed; both backends retained for operator recovery" >&2
      fi
    elif $candidate_started; then
      systemctl stop "$unit" || true
    fi
  fi
  [[ -z $stage ]] || rm -rf -- "$stage"
  rm -f -- "$route_backup"
  exit "$code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ ! -f $release/.prepared ]]; then
  $rollback && die 'Rollback release is incomplete'
  [[ ! -e $release ]] || die "Incomplete release at $release"
  stage=$release
  mkdir "$stage"
  chown timmy:timmy "$stage"
  echo "Preparing $requested with isolated Python and Node dependencies"
  git -C "$REPOSITORY" archive "$requested" | runuser -u timmy -- tar -xf - -C "$stage"
  if $bridge; then
    # The old application does not use the new receipt table. Only broaden its
    # readiness probe for the two explicitly supported schema revisions.
    runuser -u timmy -- env PATH="$BUILD_PATH" python3.12 - "$stage/backend/timmy/routes.py" <<'PYTHON'
import sys
from pathlib import Path

routes = Path(sys.argv[1])
source = routes.read_text()
old = "WHERE version_num = '0016'"
assert source.count(old) == 1
routes.write_text(source.replace(old, "WHERE version_num IN ('0016', '0017')"))
PYTHON
    touch "$stage/.schema-bridge"
  fi
  runuser -u timmy -- env PATH="$BUILD_PATH" bash -c '
    set -e
    cd "$1"
    python3.12 -m venv .venv
    .venv/bin/python -m pip install --quiet -r backend/requirements.txt
    npm ci --prefix frontend
    VITE_API_URL=/api npm run build --prefix frontend
    test -s frontend/dist/index.html
  ' _ "$stage"
  if [[ -d $LEGACY_WEB/assets ]]; then
    install -d "$stage/frontend/dist/assets"
    rsync -rt --ignore-existing "$LEGACY_WEB/assets/" "$stage/frontend/dist/assets/"
  fi
  if [[ -L $base/current ]]; then
    rsync -rt --ignore-existing "$base/current/frontend/dist/assets/" "$stage/frontend/dist/assets/"
  fi
  chmod 755 "$stage" "$stage/frontend" "$stage/frontend/dist"
  chmod -R a+rX "$stage/frontend/dist"
  ln -s "$base/shared/.env" "$stage/.env"
  ln -s "$base/shared/logs" "$stage/logs"
  touch "$stage/.prepared"
  stage=
fi

revision=$(sqlite3 -readonly "$DATABASE" 'SELECT version_num FROM alembic_version')
expected=$(runuser -u timmy -- "$release/.venv/bin/python" -m alembic -c "$release/backend/alembic.ini" heads | awk '{print $1}')
if $migrate; then
  [[ $expected == "$to_revision" && ( $revision == "$from_revision" || $revision == "$to_revision" ) ]] ||
    die 'Declared migration differs from the live schema or candidate head'
fi
if [[ $revision != "$expected" ]]; then
  if $migrate && [[ $revision == "$from_revision" && $expected == "$to_revision" ]]; then
    echo "Reviewed additive migration $from_revision -> $to_revision"
  elif $compatible_rollback && [[ $revision == "$to_revision" && $expected == "$from_revision" ]]; then
    echo "Rollback release supports schema $revision"
  elif [[ $revision == 0017 && -f $release/.schema-bridge ]]; then
    echo 'Bridge is compatible with 0017'
  else
    die 'Live schema differs from candidate; no automatic schema change'
  fi
fi
backup=$(mktemp "$base/backups/timmy.XXXXXXXX")
sqlite3 -readonly "$DATABASE" ".backup '$backup'"
[[ $(sqlite3 -readonly "$backup" 'PRAGMA integrity_check') == ok ]] || die 'SQLite backup failed integrity check'
echo 'SQLite backup verified'
if $migrate && [[ $revision == "$from_revision" ]]; then
  runuser -u timmy -- env TIMMY_DATABASE_URL="sqlite:///$DATABASE" PYTHONPATH="$release/backend" \
    "$release/.venv/bin/python" -m alembic -c "$release/backend/alembic.ini" upgrade "$to_revision"
  [[ $(sqlite3 -readonly "$DATABASE" 'SELECT version_num FROM alembic_version') == "$to_revision" ]]
  health "http://127.0.0.1:$active" || die 'Bridge health failed after additive migration'
fi
switch_link "$release" "$base/slot-$slot"
candidate_started=true
systemctl start "$unit"
wait_health "http://127.0.0.1:$slot" || die 'Standby readiness failed'
echo "Backend on $slot is ready"
if $bridge; then
  echo "Bridge ready on $slot"
elif ! $rollback; then
  git -C "$REPOSITORY" fetch --no-tags origin main
  [[ $(git -C "$REPOSITORY" rev-parse FETCH_HEAD) == "$requested" ]] ||
    die 'Commit was superseded during preparation'
else
  rsync -rt --ignore-existing "$base/current/frontend/dist/assets/" "$release/frontend/dist/assets/"
fi

# Record old workers before the reload; their connections still target the old slot.
nginx_master=$(systemctl show -p MainPID --value nginx)
[[ $nginx_master =~ ^[1-9][0-9]*$ ]] || die 'Cannot locate Nginx master'
workers=$(pgrep -P "$nginx_master" || true)
[[ -n $workers ]] || die 'Cannot identify workers to drain'
route_changed=true
write_route "$release/frontend/dist" "$slot" "$requested"
nginx -t
systemctl reload nginx
wait_health "$PUBLIC_ORIGIN" || die 'Public API health check failed'
asset=$(grep -oE '/assets/[^" ]+\.js' "$release/frontend/dist/index.html" | head -1)
[[ -n $asset ]] || die 'Candidate entry asset not found'
curl -fsS --max-time 5 "$PUBLIC_ORIGIN/" | cmp - "$release/frontend/dist/index.html"
curl -fsS --max-time 5 "$PUBLIC_ORIGIN$asset" -o /dev/null
if [[ -L $base/current ]]; then switch_link "$(readlink "$base/current")" "$base/previous"; fi
systemctl enable "$unit"
switch_link "$release" "$base/current"
echo "Deployed $requested on $slot; public backend and frontend verified"

for attempt in {1..120}; do
  draining=false
  for worker in $workers; do
    if kill -0 "$worker" 2>/dev/null; then draining=true; fi
  done
  if ! $draining; then
    systemctl disable "$active_unit" || echo "Could not disable $active_unit" >&2
    systemctl stop "$active_unit" || echo "Could not stop $active_unit" >&2
    echo "Nginx drained; retired $active_unit"
    exit 0
  fi
  sleep 2
done
echo "Nginx drain exceeded 240s; leaving $active_unit running for operator review"
