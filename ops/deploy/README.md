# Agent Timmy: GitHub Actions → Ubuntu deployment

## What is automated

- Existing `.github/workflows/ci.yml` tests PRs and pushes to `main` on GitHub-hosted runners.
- `.github/workflows/deploy.yml` triggers only after a successful **push to main** CI run, and only with repository variable `TIMMY_DEPLOY_ENABLED=true`.
- Unprivileged `timmy-deploy` fetches the exact Git SHA from `main`, builds in a new release directory, runs backend/frontend tests and a **disposable** migration, then requests activation.
- A root-owned, narrowly sudo-allowed activation script checks release readiness and live database schema, atomically switches `/srv/timmy/current`, restarts `timmy-api`, and verifies health. A failed code-only activation reverts the release symlink.
- **Schema changes are intentionally blocked**: migrate the operational database only through a separate, reviewed maintenance procedure.
- `/srv/timmy/shared` contains the private .env, database, documents and logs. Never delete it during deployment.

## Prerequisites — one-time operator setup

**Do not enable automatic deployment before finishing this checklist. Don't paste private SSH keys or passwords into chat.**

### 1. Reconcile the existing databases

There are currently two:
- `/root/apps/Timmy/timmy.db` — manually launched root process, with an additional audit event/login session.
- `/opt/timmy/timmy.db` — originally copied application database.

Existing backups are `/root/timmy-original-20261114-204033.db` and `/root/timmy-deployed-20261114-204033.db`. Compare **all relevant records**, not only table counts; identify the authoritative database. Keep both backups. Before changing the API service, gracefully stop root's manually started Uvicorn process and confirm 8000 is free. Make another consistent SQLite backup with `sqlite3 source.db ".backup 'backup.db'"`.

### 2. Prepare host tools and Linux accounts

Install `git`, `openssh-client`, `python3-venv`, `python3-pip`, `sqlite3`, `curl`, `rsync`, `util-linux`, `nginx`, and a **system-wide Node.js >=22.12** and npm. Root's nvm installation is not sufficient for the non-root deployment account.

As root, after checking the accounts/paths do not already exist:

```bash
useradd -m -s /bin/bash timmy-deploy
install -d -m 700 -o timmy-deploy -g timmy-deploy /home/timmy-deploy/.ssh
install -d -m 755 /srv/timmy
install -d -m 755 -o timmy-deploy -g timmy-deploy /srv/timmy/releases
install -d -m 700 -o timmy -g timmy /srv/timmy/shared
install -d -m 700 -o timmy -g timmy /srv/timmy/shared/documents /srv/timmy/shared/logs
```

Do **not** put `timmy-deploy` in the `sudo` or `timmy` Linux groups.

### 3. Install reviewed deployment scripts

After this PR is reviewed and merged:

```bash
git -C /root/apps/Timmy pull --ff-only origin main
cd /root/apps/Timmy
install -o root -g root -m 755 ops/deploy/stage-release.sh /usr/local/bin/timmy-stage-release
install -o root -g root -m 755 ops/deploy/receive.sh /usr/local/bin/timmy-receive
install -o root -g root -m 750 ops/deploy/activate-release.sh /usr/local/sbin/timmy-activate-release
printf '%s\n' 'timmy-deploy ALL=(root) NOPASSWD: /usr/local/sbin/timmy-activate-release *' > /etc/sudoers.d/timmy-deploy
chmod 440 /etc/sudoers.d/timmy-deploy
visudo -cf /etc/sudoers.d/timmy-deploy
```

The root activation script validates that it receives exactly one 40-character hexadecimal SHA, and is executable only through the restricted sudo rule.

### 4. Configure **two separate** SSH credentials

**Read-only server → GitHub deploy key:**
Generate an SSH key **as `timmy-deploy`** at `/home/timmy-deploy/.ssh/github_readonly`. Add only the **public key** under GitHub repository **Settings → Deploy keys**, with *Allow write access* **unchecked**. Populate `/home/timmy-deploy/.ssh/known_hosts` with GitHub's **verified** host key. Check fingerprints against GitHub's published values, not unverified `ssh-keyscan` output.

**GitHub Actions → server trigger key:**
Generate a different key on CN's trusted workstation. Put its **public key** in `/home/timmy-deploy/.ssh/authorized_keys`, prefixing it with:

```text
restrict,command="/usr/local/bin/timmy-receive"
```

The complete entry is the prefix followed by a space and the public key. Make the .ssh directory 700 and authorized_keys 600, both owned by `timmy-deploy`. Add its **private key** as secret `TIMMY_DEPLOY_SSH_KEY` in GitHub's **production environment**.

Verify the server host key against a fingerprint seen from the server console/trusted admin channel. Save a corresponding known_hosts entry in secret `TIMMY_DEPLOY_KNOWN_HOSTS`. Never disable `StrictHostKeyChecking`.

### 5. Stage the first release without changing production

```bash
sha=$(git -C /root/apps/Timmy rev-parse HEAD)
sudo -u timmy-deploy /usr/local/bin/timmy-stage-release "$sha" --stage-only
```

Do not proceed unless the release build, backend tests, ephemeral migrations, frontend tests and build all succeed.

### 6. Migrate persistent data during a maintenance window

Stop manual Uvicorn gracefully; confirm port 8000 is free; keep `timmy-api` stopped. Back up the **authoritative** DB using SQLite `.backup` and populate `/srv/timmy/shared/timmy.db` from it (don't copy a changing DB file with `cp`). Migrate private documents from the old `.timmy-data/documents` location if any, and logs where appropriate. Keep previous installs and backups unchanged.

Copy `/opt/timmy/.env` to `/srv/timmy/shared/.env`; ensure exactly one entry for each:

```dotenv
TIMMY_DATABASE_URL=sqlite:////srv/timmy/shared/timmy.db
TIMMY_DOCUMENT_ROOT=/srv/timmy/shared/documents
TIMMY_OLLAMA_URL=http://127.0.0.1:11434
TIMMY_OLLAMA_MODEL=qwen3.5:4b-q4_K_M
TIMMY_WEEKLY_ENABLED=false
```

Retain a valid browser origin. `TIMMY_COOKIE_SECURE=false` is allowed **only for localhost SSH-tunnel testing**. For public use, require an exact HTTPS origin and `TIMMY_COOKIE_SECURE=true`.

The shared directory and child private directories must be `timmy:timmy` and mode 700; `.env` and database mode 600.

### 7. Activate the first release manually

After verifying schema revision matches:

```bash
sha=$(git -C /root/apps/Timmy rev-parse HEAD)
ln -s "/srv/timmy/releases/$sha" /srv/timmy/current
```

Change only these two fields in `/etc/systemd/system/timmy-api.service`:

```ini
WorkingDirectory=/srv/timmy/current
ExecStart=/srv/timmy/current/.venv/bin/uvicorn timmy.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Keep `User=timmy`, `Group=timmy`, and existing sandboxing. Then:

```bash
systemctl daemon-reload
systemctl enable --now timmy-api
curl -fsS http://127.0.0.1:8000/api/health
```

If health fails, restore the old systemd unit and stop. **Do not enable CD.**

Once API checks pass, switch only the static Nginx web root (current Nginx uses `/var/www/timmy`):

```bash
stamp=$(date -u +%Y%m%d-%H%M%S)
mv /var/www/timmy "/var/www/timmy.before-cicd-$stamp"
ln -s /srv/timmy/current/frontend/dist /var/www/timmy
nginx -t && systemctl reload nginx
curl -fsS http://127.0.0.1/api/health
```

Verify Nginx can traverse all directories under `/srv/timmy/releases`. Validate a browser login and AI request **only over an encrypted channel**.

### 8. Enable the GitHub trigger

Create GitHub **Environment** `production`; configure secrets there. Set repository Actions variables:

| Variable | Value |
| --- | --- |
| `TIMMY_DEPLOY_HOST` | Server hostname/IP |
| `TIMMY_DEPLOY_PORT` | SSH port, typically 22 |
| `TIMMY_DEPLOY_ENABLED` | `false` during bootstrap; `true` only when validated |

Set branch protection/rulesets on `main` to require CI checks, a PR, review, and no force-push (subject to repository plan availability). Restrict the `production` environment to main, if available. CI must succeed before deploy. Never place application secrets in workflow YAML.

Merge a small non-schema-changing PR and observe **CI → Deploy**. Verify `/srv/timmy/deployed-sha`, the systemd process on 8000, Nginx health, and browser login. Test rollback safely on an isolated environment before relying on it.

## Safety limits

- The GitHub workflow cannot SSH as root. The deployment SSH key can invoke only `deploy <sha>`.
- `timmy-deploy` cannot read `/srv/timmy/shared` or modify an already activated root-owned release.
- Deployment refuses a target SHA that is no longer current `main`, and refuses live schema-version mismatches.
- Code-only rollback does **not** roll back database content. Backups and migration recovery require separate operational procedures.
- `/srv/timmy/releases` retains old releases. Do not prune until retention policy is defined.
- Local API and Ollama must remain on 127.0.0.1.
- Public HTTP is currently unsafe for application authentication; finish HTTPS before real use.
