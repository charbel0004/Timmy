# Agent Timmy — simple hackathon CI/CD

**MVP decision:** one application checkout (`/root/apps/Timmy`), one FastAPI service, and existing Nginx static directory (`/var/www/timmy`). No release or staging directory trees. Test files use only disposable `/tmp` directories.

## GitHub flow

1. Existing `ci.yml` runs backend tests, frontend tests/build, and migrations on PRs and `main`.
2. `deploy.yml` triggers **only** after a successful push-to-`main` CI run and `TIMMY_DEPLOY_ENABLED=true`.
3. GitHub Actions SSH uses `timmy-deploy` with a **forced command** permitting only `deploy <40-character SHA>`.
4. Root-owned `/usr/local/sbin/timmy-deploy` checks `main` equals the tested SHA, stops FastAPI, takes a consistent offline SQLite backup, updates the *single* checkout, re-installs Python deps using uv, runs tests and disposable migrations from an isolated temporary source copy with a sanitized environment, applies only the allowlisted additive 0016→0017 migration when necessary, builds React with `VITE_API_URL=/api`, syncs static files, restarts systemd, verifies health. On failure, it restores the previous code and frontend and, when a live schema upgrade was attempted, restores the offline database backup before restarting the previous backend. It refuses to restart if database recovery verification fails. No arbitrary schema migrations are allowed.

**Trade-off:** in-place deployment causes a short maintenance window, and rollback is best-effort. Appropriate for the hackathon MVP, not a zero-downtime production design.

## One-time setup — do not enable CD until completed

### A. Confirm which database is authoritative

Original `/root/apps/Timmy/timmy.db` had one extra audit event and one active login session versus `/opt/timmy/timmy.db`. Other records have been verified to match by the operator. Preserve the previously made backups, including `/root/timmy-original-20261114-204033.db` and `/root/timmy-deployed-20261114-204033.db`. For the one-checkout approach, use `/root/apps/Timmy/timmy.db` as the authoritative database, preserving audit evidence. Do not overwrite it with the older deployed copy. This will invalidate nothing automatically; existing sessions may be expired or revoked separately.

### B. Make systemd the only backend owner

Manual root Uvicorn was started using:

```bash
cd /root/apps/Timmy
.venv/bin/python -m uvicorn backend.timmy.main:app --host 127.0.0.1 --port 8000
```

This is the **confirmed import path**. Stop this manual process gracefully (CN can press Ctrl+C) and verify port 8000 is free. If any real users are active, schedule a brief maintenance window.

Replace `/etc/systemd/system/timmy-api.service` with:

```ini
[Unit]
Description=Agent Timmy FastAPI (hackathon)
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/apps/Timmy
Environment=PYTHONUNBUFFERED=1
ExecStart=/root/apps/Timmy/.venv/bin/python -m uvicorn backend.timmy.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

The choice of root service user is a conscious MVP trade-off because the existing checkout is under `/root`; moving it to a non-root checkout would be safer. Never expose port 8000 publicly. Run:

```bash
systemctl daemon-reload
systemctl enable --now timmy-api
systemctl is-active timmy-api
ss -ltnp '( sport = :8000 )'
curl -fsS http://127.0.0.1:8000/api/health
```

The PID listening on 8000 must match `systemctl show timmy-api -p MainPID`.

### C. Install protected scripts and dependencies

On the server as root (after PR merge), run:

```bash
cd /root/apps/Timmy
git fetch origin main
git reset --hard origin/main
install -o root -g root -m 700 ops/deploy/deploy-server.sh /usr/local/sbin/timmy-deploy
install -o root -g root -m 755 ops/deploy/receive.sh /usr/local/bin/timmy-receive
command -v rsync git sqlite3 curl flock
test -x /root/.local/bin/uv
test -x /root/apps/Timmy/.venv/bin/python
```

Ensure Node.js 22 and npm are installed for root, including in non-interactive system sessions (the script loads root nvm where available). Verify Nginx is serving `/var/www/timmy`.

### D. Restrict SSH GitHub Actions trigger

Create `timmy-deploy` as a **non-sudo** service account:

```bash
id timmy-deploy || useradd -m -s /bin/bash timmy-deploy
install -d -o timmy-deploy -g timmy-deploy -m 700 /home/timmy-deploy/.ssh
```

Generate a dedicated Ed25519 key pair on CN's trusted computer; put its **public** key in `/home/timmy-deploy/.ssh/authorized_keys` prefixed by:

```text
restrict,command="/usr/local/bin/timmy-receive"
```

Owner `timmy-deploy:timmy-deploy`, mode 600 for authorized_keys. Do not paste private keys or passwords into chat.

Allow only the validated root-owned deployer to run via sudo:

```bash
printf '%s\n' 'timmy-deploy ALL=(root) NOPASSWD: /usr/local/sbin/timmy-deploy *' >/etc/sudoers.d/timmy-deploy
chmod 440 /etc/sudoers.d/timmy-deploy
visudo -cf /etc/sudoers.d/timmy-deploy
```

The deployer accepts **exactly** one 40-character hexadecimal SHA and checks it against GitHub main. The SSH account must not have general sudo membership.

Verify the Ubuntu host's SSH public host key fingerprint through the trusted server console. Store the verified `known_hosts` line as GitHub environment secret `TIMMY_DEPLOY_KNOWN_HOSTS`. Store the trigger key **private** contents as environment secret `TIMMY_DEPLOY_SSH_KEY`.

### E. GitHub configuration

Create environment `production` with branch restriction `main` where available.

Repository Actions variables:
- `TIMMY_DEPLOY_HOST`: public IP or hostname
- `TIMMY_DEPLOY_PORT`: port (typically `22`)
- `TIMMY_DEPLOY_ENABLED`: **false** until initial manual verification; then **true**

CI actions must pass and `main` should be PR-protected.

### F. First controlled test and activation

After the service is healthy, **do not run the deploy script for the currently checked-out commit**, because it will exit as already deployed. Instead, make a harmless PR that changes a UI string or documentation, merge after green CI, and only then activate `TIMMY_DEPLOY_ENABLED=true` for a subsequent small PR to exercise CD.

If CD fails, leave it disabled, examine the GitHub job logs and `journalctl -u timmy-api`, and confirm the API health endpoint. Never reset or delete SQLite to fix a pipeline issue.

## Security & data precautions

- `.env` and `timmy.db` remain ignored, local, and uncommitted.
- Keep backup files owned by root and outside the public web root.
- `TIMMY_COOKIE_SECURE=false` with public port 80 is unsafe for login. Use SSH tunneling until HTTPS and `TIMMY_COOKIE_SECURE=true` are configured.
- Production schema upgrades are **fail-closed by default**. The deployment script explicitly allows only previously reviewed additive migration **0016 → 0017** as part of an exact-SHA rollout, after stopping the API and taking a consistent offline SQLite backup. It restores the backup if deployment fails. Any later migration requires separate code review and an updated allowlist.
- The production server runs a **root-owned installed copy** of the deployment script at `/usr/local/sbin/timmy-deploy`. **CN must review and reinstall the updated script manually** before attempting the next automatic deployment; merging repository changes alone cannot update the installed root script. The forced-command SSH account must remain unchanged.
- A failed previous deployment may have left `timmy-api` unhealthy despite resetting the Git checkout. CN must verify `systemctl is-active timmy-api`, listener ownership, `/api/health`, and the live database revision before re-enabling the pipeline. Do not reset or migrate the live DB until that health check passes.
- The in-place rollout will cause brief downtime during dependency installation and tests. This is an explicit MVP trade-off.
- Root-run backend increases risk; preserve loopback-only API/Ollama, restricted SSH, and no broad sudo for deployment account.

## Explicit CD recovery gate (November 2026)

1. CN verifies the API is healthy at the previous version and confirms **`timmy.db`** in the single root checkout is the authoritative live SQLite database. Do not overwrite it from an older backup.
2. CN installs reviewed `ops/deploy/deploy-server.sh` as `/usr/local/sbin/timmy-deploy` with root ownership and mode 700. No SSH deploy permission change is required.
3. On the next verified main SHA, the script stops the API, takes an **offline** SQLite `.backup`, validates integrity and foreign keys, then tests against an isolated source copy with no production `.env`. Production settings cannot contaminate tests.
4. Only when current revision is **0016** and target is **0017**, the script applies the known additive migration to the live DB while the API is stopped and revalidates the exact revision, `integrity_check`, and `foreign_key_check`. If already 0017, no live migration is attempted. Other mismatches are blocked.
5. On any failed deployment after migration starts, the script restores code, frontend, and the **offline DB backup**. If DB restoration fails, it leaves the API stopped and prints the backup path for CN's manual recovery. The GitHub job must remain failed.
6. Finally, CN verifies API health and migration revision, and records the live SHA. GitHub CI passing by itself does not prove a healthy server.
