# Timmy production deployment

A successful push-triggered CI run on `main` launches the production workflow when `TIMMY_DEPLOY_ENABLED=true` and `TIMMY_DEPLOY_V2_READY=true`. CI tests and migrates a disposable database. The deployed SSH key invokes the restricted receiver with the exact tested SHA. The server checks that SHA against `origin/main`, prepares it as the non-root `timmy` user, and routes traffic only after standby readiness. GitHub concurrency and a server lock serialize deploys.

## Inspect the existing host

Run these read-only commands in the existing administrator session. Inspect any sensitive output locally.

```sh
sudo ss -ltnp '( sport = :80 or sport = :8000 or sport = :8001 or sport = :11434 )'
sudo systemctl show timmy-api -p MainPID -p User -p WorkingDirectory -p FragmentPath
sudo nginx -T
sudo git -C /root/apps/Timmy rev-parse HEAD
sudo find /root/apps/Timmy -maxdepth 2 -type d
sudo lsof -nP -p "$(sudo systemctl show timmy-api -p MainPID --value)"
```

Resolve settings under the running service's user, working directory and environment. Compare the result with its open file descriptors. The following command covers the original root service when systemd supplies no settings overrides.

```sh
sudo bash -c 'cd /root/apps/Timmy && PYTHONPATH=backend .venv/bin/python -' <<'PY'
from pathlib import Path
from sqlalchemy.engine import make_url
from timmy.config import settings

config = settings()
url = make_url(config.database_url)
assert url.get_backend_name() == "sqlite" and url.database
print("SQLite:", Path(url.database).resolve())
print("Documents:", config.document_root.expanduser().resolve())
print("Origin:", config.frontend_origin)
print("Weekly scheduler:", config.weekly_enabled)
print("Voice cache:", config.whisper_cache.expanduser().resolve())
print("Voice model:", config.piper_model.expanduser().resolve())
PY
```

Verify the database revision with `sqlite3 -readonly "$DATABASE" 'SELECT version_num FROM alembic_version'`. Inspect systemd and Nginx settings locally before choosing paths. Account for overrides, additional mount points, uploaded documents, backups, logs, and model caches. Keep both preexisting database copies until the authoritative one is confirmed.

## Bootstrap on the existing host

1. Temporarily set the GitHub repository variable `TIMMY_DEPLOY_ENABLED=false` before merging this change. Keep the existing service and site running while preparing the new layout.
2. Create a dedicated system user and group named `timmy` with no login or sudo. Create root-owned `/opt/timmy-deploy`, `releases`, and `backups`. Allow directory traversal to releases and keep backups root-only. Prepare `/opt/timmy-deploy/shared/{data,uploads,logs}`. Use the actual storage found above. Copy the production `.env` byte-for-byte to `shared/.env` with owner root, group timmy and mode 0640. Preserve Ollama's service and data. If voice is enabled, make its existing model and cache available to the new user.
3. Use a consistent SQLite `.backup` and check it with `PRAGMA integrity_check`. Initial storage relocation needs a coordinated write freeze and final database backup and document sync. During that freeze, configure the legacy backend and new slots to use the **same** verified writable database and document paths before resuming traffic. Copy logs independently and preserve the originals. If the existing live paths are already accessible to the non-root user, point both services there and skip relocation. Never sync a stale database over live writes. Keep the original checkout, configuration, and backup. Once writes resume, legacy rollback must use the shared authoritative data.
4. Create root-owned `/etc/timmy/deploy.conf` with mode 0600. Set `REPOSITORY` to the verified Git checkout for fetching, `DATABASE` to the absolute shared SQLite file, `PUBLIC_ORIGIN` to `http://157.230.128.215`, `NGINX_INCLUDE` to `/etc/timmy/nginx-active.conf`, and `LEGACY_UNIT`, `LEGACY_WEB` and `LEGACY_SHA` to their inspected values. Set `BUILD_PATH` to the normal system path plus Node.js 22 installed where `timmy` can execute it. Verify Python 3.12, venv, npm, git, sqlite3, rsync, flock and curl. Ensure the original service owns port 8000 and port 8001 is free.
5. Create root-owned `/etc/timmy/runtime.conf` with mode 0600, using systemd EnvironmentFile syntax. Set `TIMMY_DATABASE_URL=sqlite:////opt/timmy-deploy/shared/data/timmy.db` and `TIMMY_DOCUMENT_ROOT=/opt/timmy-deploy/shared/uploads` only if those are the verified shared paths. Set `TIMMY_EXPECTED_DATABASE` to the same absolute database file and `TIMMY_EXPECTED_ORIGIN=http://157.230.128.215`. Confirm the database parent, uploads and logs are writable by `timmy`. Preserve authentication, origin and Ollama configuration. Both backends must have the weekly scheduler off during overlap. The runtime check rejects an enabled scheduler pending a singleton scheduling strategy.
6. Add `include /etc/timmy/nginx-active.conf;` inside the existing site `server` block. Move the site's existing static root directive to that include, preserving any existing SPA routing. Add these lines above it, substituting the inspected commit:

   ```nginx
   # 8000 <legacy-40-character-sha>
   set $timmy_backend http://127.0.0.1:8000;
   ```

   Change the existing API location's upstream to `proxy_pass $timmy_backend;` if it currently preserves the request URI. If it rewrites paths, reproduce and test its URI behavior before proceeding. Preserve proxy headers, TLS, and streaming configuration. Do not set a short Nginx worker shutdown timeout. Run `sudo nginx -t && sudo systemctl reload nginx`, then verify the original public API and frontend. Keep a copy of the original site configuration.
7. Install the reviewed files from a separate checkout, with root as owner. Keep the receiver and constrained sudoers rule for `timmy-deploy`.

   ```sh
   sudo install -d -m 755 /usr/local/libexec
   sudo install -o root -g root -m 700 ops/deploy/deploy-server.sh /usr/local/sbin/timmy-deploy
   sudo install -o root -g root -m 755 ops/deploy/receive.sh /usr/local/bin/timmy-receive
   sudo install -o root -g root -m 755 ops/deploy/check-runtime.py /usr/local/libexec/timmy-check-runtime
   sudo install -o root -g root -m 644 ops/deploy/timmy-api@.service /etc/systemd/system/
   sudo systemctl daemon-reload
   ```

8. If the active release is still on revision `0016`, run `sudo /usr/local/sbin/timmy-deploy --bridge`. This builds the verified legacy SHA and changes only the health check to accept both `0016` and `0017`. Verify the bridge on port 8001 before enabling the pipeline. The first candidate may apply the reviewed, pinned additive receipt migration while the bridge serves requests. The existing authoritative storage under `/opt/timmy` can remain in place. Keep the new release metadata under root-owned `/opt/timmy-deploy`.
9. Configure production environment secrets `TIMMY_DEPLOY_SSH_KEY` and `TIMMY_DEPLOY_KNOWN_HOSTS` from the dedicated restricted key and the verified host key. Verify repository variables `TIMMY_DEPLOY_HOST` and `TIMMY_DEPLOY_PORT`. Set both deployment variables to true and rerun the verified push CI. Observe a long-running request during the switch and verify existing sessions, documents, frontend assets, and production health.

## Operation and rollback

- `/api/live` checks the process. `/api/health` checks database access and the required schema revision. Systemd validates effective configuration before startup.
- The deployer checks for an unchanged Alembic tree and exact revision match, then takes and verifies a consistent SQLite backup. The only automatic schema change is the pinned additive migration from 0016 to 0017 with the compatible bridge active. Other pending, rewritten or unreviewed migrations fail closed. Plan schema changes separately using expand-and-contract compatibility or a maintenance window. The deployer never restores a backup over live writes.
- The backend and frontend switch together in one atomically replaced Nginx include. Production assets use `/api` and older hashes are carried forward. The deployer checks the public HTML and entry asset. Keep release directories and their assets until an operator has verified they are outside the retention window and unreferenced by current, previous, either slot, or active Nginx workers. There is no automated deletion of completed releases.
- The deployment waits for the old Nginx worker processes to exit before stopping the previous backend. Weekly background scheduling must be off. If old workers remain after four minutes, the previous service stays up and the next deploy refuses to reuse its port. Verify the workers and any direct loopback traffic have drained before disabling and stopping that service.
- A failed readiness check leaves the original route in place. A post-switch failure restores the saved routing when the old backend is healthy. The candidate stays up to drain. Inspect Nginx workers before stopping it. If automatic restoration fails, leave both slots running and repair routing from the last verified release.
- After two versioned releases, run `sudo /usr/local/sbin/timmy-deploy --rollback` (or `sudo ops/deploy/rollback.sh`) to health-check the retained release on the standby slot and switch back. For the initial migration, rollback manually using the saved legacy Nginx configuration and original service, confirming that it still points to the authoritative shared database and document directory. Rollback never rewinds the database.
