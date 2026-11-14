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

## Stored workflows

Select a project in Context and use brief requests such as `Analyze`, `Process`,
`Run weekly`, `Show flags`, or `Reconcile the payment report`. Procedures are
stored in `backend/timmy/workflow_knowledge.json`; the user supplies the goal,
not the steps. Analyze verifies already-uploaded intake and offers processing.
Runs preserve evidence references and per-step outcomes. Missing authoritative
validation, resolution and financial adapters remain explicit blockers.

Weekly scheduling is off by default. To enable it, set
`TIMMY_WEEKLY_ENABLED=true`, an authorized `TIMMY_WEEKLY_ACTOR_ID`, and an
explicit `TIMMY_WEEKLY_PROJECT_IDS` list. It runs once per project on Mondays
at 04:00 Asia/Beirut and catches up later that Monday. Apply
migration 0013 before starting the updated app. Payment requests are intended as
files for the coordinator to send manually; the required approved-batch export
adapter is not yet implemented, and no automatic external delivery occurs.

See [workflow triggers and remaining integrations](docs/ai/WORKFLOW_TRIGGERS.md).

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

Assistant requests show a live activity trail in chat, including the action the
local model selected. Open **Assistant activity** on a new reply to see its
steps and request ID. The same ID appears in the local diagnostic log at
`logs/assistant.log` in the project folder.
The log rotates at 1 MB and keeps three backups. It records timings, action
names and failure codes without storing prompts, replies or spreadsheet data.
Activity on individual replies is available in the current view; reloading
chat history does not restore the activity trail.


## Conversation confirmation

After Analyze, reply Yes to review a persisted mapping proposal, then Confirmed
to run structural checks. Missing/ambiguous fields are editable in the mapping
review panel. Is it done? and where is it? read persisted results, not model
status claims. Revise column mappings creates a new review version without
overwriting the confirmed one. Scope and state survive reopening the conversation;
identity, planning, external reports and payments retain their separate gates.
See [repair report](docs/architecture/conversation-workflow-repair.md).
