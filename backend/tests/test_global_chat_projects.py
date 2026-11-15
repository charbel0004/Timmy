"""Synthetic multi-project intake: chat is global, source evidence resolves projects."""
from uuid import uuid4

from sqlalchemy import insert, update, select, func
from sqlalchemy.orm import Session

from test_foundation import ORIGIN, PASSWORD, client
from timmy.auth import password_hasher
from timmy.models import Role, User, WorkflowRun, project_memberships, projects, StoredFile


def test_global_chat_upload_maps_both_projects_and_stops_financial_work(client, tmp_path, monkeypatch):
    from timmy.ai import OllamaAdapter

    async def unexpected(*args, **kwargs):
        raise AssertionError("Global project discovery is deterministic; no model tool authority")
    monkeypatch.setattr(OllamaAdapter, "structured", unexpected)
    client.app.state.config.document_root = tmp_path / "uploaded"
    with Session(client.app.state.engine) as db, db.begin():
        role = Role(name="admin")
        db.add(role)
        db.flush()
        db.add(User(id=93, username="global-timmy-admin", role_id=role.id,
                    password_hash=password_hasher.hash(PASSWORD)))
        db.flush()  # The membership FK must reference a persisted synthetic user.
        db.execute(update(projects).where(projects.c.id == 1)
                   .values(name="Training Project", project_code="TCD", policy_family="session"))
        db.execute(update(projects).where(projects.c.id == 2)
                   .values(name="Field Support", project_code="FOS", policy_family="hours"))
        for pid in (1, 2):
            db.execute(insert(project_memberships).values(project_id=pid, user_id=93))

    login = client.post("/api/auth/login", headers=ORIGIN,
                        json={"username": "global-timmy-admin", "password": PASSWORD})
    assert login.status_code == 200, login.text
    headers = ORIGIN | {"X-CSRF-Token": login.json()["csrf_token"]}
    cid = client.post("/api/chat/conversations", headers=headers).json()["id"]

    csv = ("project_code,activity_code,approved_start_date,approved_end_date\n"
           "TCD,26-TCD-001,2026-09-01,2026-09-30\n"
           "FOS,26-FOS-001,2026-09-01,2026-09-30\n"
           "BAD,26-BAD-999,2026-09-01,2026-09-30\n")
    uploaded = client.post("/api/documents", params={"filename":"planning.csv","conversation_id":cid},
                           content=csv.encode(), headers=headers | {"Content-Type":"text/csv"})
    assert uploaded.status_code == 201, uploaded.text
    doc = uploaded.json()
    assert doc["project_id"] is None

    def message(text):
        reply = client.post(f"/api/chat/conversations/{cid}/messages", headers=headers,
                            json={"message":text,"request_id":str(uuid4())})
        assert reply.status_code == 200, reply.text
        return reply.json()["message"]["text"]

    analyzed = message("Analyze these files")
    assert "Training Project (TCD): 1" in analyzed
    assert "Field Support (FOS): 1" in analyzed
    assert "UNKNOWN_PROJECT_CODE: 1" in analyzed
    assert "Only intake/routing is verified" in analyzed
    processed = message("Process both project timesheets")
    assert "MULTI_PROJECT_VALIDATION_ADAPTER_REQUIRED" in processed
    assert "No cross-project source registration" in processed
    assert "check_planning" in processed
    state = client.get(f"/api/chat/conversations/{cid}/workflow")
    assert state.status_code == 200, state.text
    global_state = state.json()
    assert global_state["stage"] == "GLOBAL_WORKFLOW_RECORDED"
    assert global_state["scope"]["project_ids"] == [1, 2]
    assert len(global_state["project_runs"]) == 2
    assert all(run["status"] == "blocked" for run in global_state["project_runs"])
    status_text = message("Is it done?")
    assert "Recorded global workflow status" in status_text
    assert "run #" in status_text
    history = client.get(f"/api/chat/conversations/{cid}").json()
    assert "MULTI_PROJECT_VALIDATION_ADAPTER_REQUIRED" in history["messages"][-3]["text"]

    with Session(client.app.state.engine) as db:
        runs = db.scalars(select(WorkflowRun).order_by(WorkflowRun.id)).all()
        assert [(run.project_id, run.workflow_id, run.status) for run in runs] == [
            (1, "analyze_intake", "completed"),
            (2, "analyze_intake", "completed"),
            (1, "process_activity", "blocked"),
            (2, "process_activity", "blocked"),
        ]
        assert all(run.snapshot["payment_authority"] == "none" for run in runs)
        saved = db.get(StoredFile, doc["id"])
        assert saved is not None and saved.project_id is None

    other = client.post("/api/chat/conversations", headers=headers).json()["id"]
    response = client.get("/api/documents", params={"conversation_id":other})
    assert response.status_code == 200
    assert response.json() == []
