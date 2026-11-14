# Agent Timmy — simple hackathon CI/CD

**MVP decision:** one application checkout (`/root/apps/Timmy`), one FastAPI service, and existing Nginx static directory (`/var/www/timmy`). No release or staging directory trees. Test files use only disposable `/tmp` directories.

## GitHub flow

1. Existing `ci.yml` runs backend tests, frontend tests/build, and migrations on PRs and `main`.
2. `deploy.yml` triggers **only** after a successful push-to-`main` CI run and `TIMMY_DEPLOY_ENABLED=true`.
3. GitHub Actions SSH uses `timmy-deploy` with a **forced command** permitting only `deploy <40-character SHA>`.
4. Root-owned `/usr/local/sbin/timmy-deploy` checks `main` equals the tested SHA, backs up SQLite, temporarily stops FastAPI, updates the *single* checkout, re-installs Python deps using uv, runs tests and a disposable migration, builds React with `VITE_API_URL=/api`, syncs static files, restarts systemd, verifies health. On failure, it attempts to restore the previous code and frontend. It **does not roll back database schema**.

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
- Automated database migrations on the real database are **disabled**. Schema changes require manual review, a consistent backup and a coordinated migration.
- The in-place rollout will cause brief downtime during dependency installation and tests. This is an explicit MVP trade-off.
- Root-run backend increases risk; preserve loopback-only API/Ollama, restricted SSH, and no broad sudo for deployment account.
