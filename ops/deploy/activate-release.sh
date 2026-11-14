#!/usr/bin/env bash
# Installed root-owned at /usr/local/sbin/timmy-activate-release.
# Permitted via narrow sudoers rule ONLY for timmy-deploy.
set -Eeuo pipefail
umask 022
if [[ $EUID -ne 0 || $# -ne 1 || ! "$1" =~ ^[0-9a-f]{40}$ ]]; then
  echo 'Usage (root): timmy-activate-release <40-character-SHA>' >&2
  exit 2
fi
sha="$1"
root=/srv/timmy
release="$root/releases/$sha"
shared="$root/shared"
current="$root/current"

[[ -f "$release/.timmy-ready" && -s "$release/frontend/dist/index.html" ]] || exit 1
[[ -x "$release/.venv/bin/python" && -f "$release/.timmy-schema-revision" ]] || exit 1
[[ "$(readlink "$release/.env")" == "$shared/.env" ]] || exit 1
[[ "$(readlink "$release/timmy.db")" == "$shared/timmy.db" ]] || exit 1
[[ -f "$shared/.env" && -f "$shared/timmy.db" ]] || exit 1

# No automatic schema migrations: they can make code rollback unsafe.
existing_revision="$(sqlite3 "$shared/timmy.db" 'SELECT version_num FROM alembic_version LIMIT 1')"
release_revision="$(cat "$release/.timmy-schema-revision")"
if [[ "$existing_revision" != "$release_revision" ]]; then
  echo "Migration gate: existing=$existing_revision release=$release_revision; manual migration review required." >&2
  exit 1
fi

exec 8>/run/lock/timmy-activation.lock
flock -w 60 8
previous="$(readlink -f "$current" 2>/dev/null || true)"
if [[ "$previous" == "$release" ]]; then
  echo "Already deployed: $sha"
  exit 0
fi

# Prevent the build identity from changing code after the release is approved.
chown -hR root:root "$release"
chmod -R go-w "$release"

systemctl stop timmy-api
ln -s "$release" "$root/.current-next-$$"
mv -Tf "$root/.current-next-$$" "$current"
if systemctl start timmy-api; then
  for _ in $(seq 1 30); do
    if curl -fsS --max-time 2 http://127.0.0.1:8000/api/health 2>/dev/null \
        | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'; then
      printf '%s\n' "$sha" > "$root/deployed-sha"
      echo "DEPLOYED $sha (schema $existing_revision)"
      exit 0
    fi
    sleep 2
  done
fi

echo 'Health verification failed; reverting code symlink (no schema change allowed).' >&2
systemctl stop timmy-api || true
if [[ -n "$previous" && -d "$previous" ]]; then
  ln -s "$previous" "$root/.current-rollback-$$"
  mv -Tf "$root/.current-rollback-$$" "$current"
  systemctl start timmy-api || true
  echo "Restored previous code: $previous" >&2
else
  echo 'No earlier release; operator recovery required.' >&2
fi
exit 1
