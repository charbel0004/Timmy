# Agent Timmy · LAU AlphaHack 2026

Local-first timesheet validation and payment preparation for volunteer projects. Phase 1 provides authentication, project-scoped access, a React workspace, and a local Ollama adapter.

## Local startup

Use Python 3.11+ and Node.js 22.12+.

```sh
cp .env.example .env
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
npm ci --prefix frontend
.venv/bin/alembic -c backend/alembic.ini upgrade head
PYTHONPATH=backend .venv/bin/python -m timmy.cli local-admin --role admin
./scripts/start-api.sh
```

In a second terminal run `npm run dev --prefix frontend` and visit [the local workspace](http://localhost:5173). Use `localhost` for both browser origins. The provisioning command prompts for a password. Configuration comes from the root `.env` or environment variables. Relative SQLite paths resolve from the command's working directory. Loopback HTTP is the default. Set `TIMMY_COOKIE_SECURE=true` when serving the API over HTTPS.

For a demo workspace, enable `TIMMY_DEMO_MODE=true` in a separate local database and provision a fresh username with `--demo-projects`. This assigns three clearly labeled sample projects to that account. Regular accounts start with zero assignments.

Ollama is optional for startup. Run Ollama locally and install the model tag configured by `TIMMY_OLLAMA_MODEL` to exercise the adapter. The adapter is a Python integration point for future ingestion. Health reports database schema readiness.

## Verification

```sh
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests
.venv/bin/alembic -c backend/alembic.ini check
npm run build --prefix frontend
curl -fsS http://localhost:8000/api/health
```

See [Phase 1 architecture and open decisions](docs/phase-1.md).

## Workspace administration

Sign in with a locally provisioned admin account. Projects supports lifecycle
changes and Users supports role and project assignment, credential resets, and
two onboarding modes. Temporary passwords require a change on first login.
Activation links expire and are shown once for private manual handoff.
`TIMMY_ACTIVATION_MINUTES` configures their lifetime (default 60 minutes).
The role matrix reflects the permissions currently enforced by the API.

## Local voice

The assistant microphone records up to 30 seconds and inserts an editable
transcript. The speaker control generates English speech for compatible replies.
Voice requests use the existing authenticated API and CSRF protection.

Use FFmpeg on PATH and install `backend/requirements-voice.txt` in the API's
Python environment. Voice uses cached multilingual Whisper small on CPU/int8
and Piper's English Lessac medium voice. See `.env.example` for cache and speed
settings. Models are kept outside the project under `~/.cache/timmy` by default.
Start the application with the same API and frontend commands above.
