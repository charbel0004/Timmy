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

### Additive schema releases

For a reviewed additive migration, update `ops/deploy/additive-migration` with one
line containing the live revision, new revision, repository-relative migration
path, and its `git hash-object` value. The runner requires exactly that one new
migration file. Keep the declaration in subsequent releases. Review that both
backends can read and write the upgraded schema during overlap, including rows
written by either version. Readiness probes should check required schema
capabilities so they continue to pass after a compatible upgrade. The runner
verifies a SQLite backup before upgrading and retains the prior app for rollback
on the upgraded database. Changes outside this contract require a separate plan.

For the first `0017 → 0018` rollout, install the updated root-owned runner using
the installation command above. The live `2c410f0` release predates compatible
readiness. With the route and current release verified as `2c410f0` on port
8000 and the database at `0017`, update that release's readiness predicate from
`WHERE version_num = '0017'` to `WHERE version_num IN ('0017', '0018')`.
Restart `timmy-api@8000.service` during a brief maintenance window and confirm
both slot and public readiness. Create the root-owned
`/opt/timmy-deploy/current/.additive-schema-compatible` marker only after
verifying the patched release. Then rerun the failed deploy for the latest
CI-verified main SHA. Subsequent additive releases use the declaration and
existing runner.

### Reviewed observability transition (0018 → 0019)

The candidate manifest now pins the exact 0019 telemetry migration blob. Relative
to active release `da97587e7f0006c6a04c79e77efbafbbfe972da3`, this is the only
migration-tree change. It adds telemetry tables and indexes without rewriting
existing business tables. Regression tests run the actual archived active backend
against the expanded database and verify health, login, and scoped project reads.
Backend CI fetches history for this compatibility regression. The existing
populated-upgrade test also verifies original rows and columns are preserved.

Use the existing verified-main deployment workflow after CI succeeds. Its existing
manifest reader checks the precise added path and Git blob, verifies live revision
0018 and candidate head 0019, backs up and checks SQLite, applies the migration,
and checks the old slot's health before switching. Do not rerun the older 7a8c6ae
candidate: its manifest still declares the previous transition. Deploy the new
verified main SHA containing this correction. No server-script reinstall or
removal of the migration gate is required when the installed deployer has the
manifest reader shown above. If the installed root-owned script predates that
reader, install the reviewed deploy script through the existing operator process.

For rollback, retain schema 0019 and switch application code to the compatible
0018 release using the existing rollback command. The manifest reader validates
the reverse relationship. Never restore a pre-migration backup over live writes.

### Browser refresh and release notices

The UI is light-only and discards the old `timmy-theme` preference. Each build
publishes `app-version.json`; open clients check it without HTTP caching on focus
and once per minute. A new release offers a Reload app button using a unique
HTML URL. It preserves the current route and does not clear login cookies or
interrupt an in-progress task with an automatic reload.

For a browser still running a release from before this update, open
`/refresh.html` once. This new entry point loads `/?_timmy_refresh=<timestamp>`
and bypasses an old HTML cache entry without requiring incognito. Previously
loaded JavaScript cannot be changed remotely until the browser navigates.

The current public Nginx response has no explicit Cache-Control for HTML. An
operator with server access should additionally set HTML responses to
`Cache-Control: no-cache` in the existing SPA location (including its index.html
fallback), then validate with `nginx -t` before reloading Nginx. Hashed Vite assets
may retain long cache lifetimes. A repository change to the deploy script alone
cannot update the installed root-owned Nginx configuration. No cache-clearing
response should remove authentication cookies or browser-stored user documents.


### Reviewed Excel workflow transition (0019 → 0020)

The candidate manifest pins only `0020_reporting_register.py`, an additive
migration creating seven reporting/payment-evidence tables. The compatibility
regression runs archived release `f203273f42b937eab8605445c89ecf759e0d6096`
against the expanded schema. CI also checks a populated upgrade and model drift.
Use the existing blob-pinned migration gate after reviewing the candidate and
successful CI; do not disable that gate to deploy a different migration tree.
The verified deployer must find live revision 0019, verify its SQLite backup,
apply 0020, and health-check both slots before switching. If live schema or
migration history differs, stop and review a separate transition.

No financial permission is granted automatically, including to administrators.
Explicitly designate the approved Excel report source and its project scopes;
assign `planning.verify`, `staff.verify`, `payments.allocate` and
`payments.approve` only to the authorized humans. Existing uploads alone do not
become report validation, human approval, or settlement. See
[the Excel workflow contract](../../docs/excel-reporting-workflow.md).

Rollback switches application code and keeps schema 0020 and its evidence.
Never restore an old backup over live writes or downgrade evidence tables after
recording approvals without an operator retention/reconciliation plan. This
change has no external payment-delivery or bank-settlement adapter.


### CI frequency

The backend tests/database checks and frontend tests/build run once on pushes to
`main`, including merged pull requests. Feature-branch pushes and pull requests
do not trigger this suite. A failure is therefore discovered after merge and
holds deployment. The existing workflow-run gate deploys only a successful
main push from this repository, bound to the exact verified SHA. This reduces
duplicate CI runs; it does not remove the checks before production deployment.
