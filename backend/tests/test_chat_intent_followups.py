"""Regression tests for documented 2026-11-15 global-chat routing failures.

These are synthetic inputs. Neither routing nor mapping review authorizes payments.
"""
from uuid import uuid4

from sqlalchemy import insert, update
from sqlalchemy.orm import Session

from test_foundation import ORIGIN, PASSWORD, client
from timmy.auth import password_hasher
from timmy.chat_routes import is_policy_lookup
from timmy.models import Role, User, project_memberships, projects
from timmy.workflows import choose_workflow


ORIGINAL_REQUEST = (
    "Process the October 2026 planning, reporting and timesheet files for both "
    "TCD and FOS. Match the activities and volunteers, normalize supported formatting, "
    "identify discrepancies, apply both payment policies, and prepare the payment "
    "requests. Do not execute payments."
)


def test_operational_policy_language_does_not_trigger_policy_lookup():
    assert is_policy_lookup("What are the payment policies for both projects?")
    assert not is_policy_lookup(ORIGINAL_REQUEST)
    assert choose_workflow(ORIGINAL_REQUEST) == "weekly_cycle"
    assert choose_workflow("Do not process the payment requests.") == "clarify"
    assert choose_workflow("Process payments") == "clarify"


def test_global_mapping_review_and_request_for_prerequisites_are_deterministic(
        client, tmp_path, monkeypatch):
    from timmy.ai import OllamaAdapter

    async def unexpected(*args, **kwargs):
        raise AssertionError("These intents must not invoke Ollama")

    monkeypatch.setattr(OllamaAdapter, "structured", unexpected)
    client.app.state.config.document_root = tmp_path / "uploaded"
    with Session(client.app.state.engine) as db, db.begin():
        role = Role(name="admin")
        db.add(role)
        db.flush()
        db.add(User(id=96, username="mapping-intent-admin", role_id=role.id,
                    password_hash=password_hasher.hash(PASSWORD)))
        db.flush()
        db.execute(update(projects).where(projects.c.id == 1).values(
            name="Training Project", project_code="TCD", policy_family="session", status="active"))
        db.execute(update(projects).where(projects.c.id == 2).values(
            name="Field Support", project_code="FOS", policy_family="hours", status="active"))
        for pid in (1, 2):
            db.execute(insert(project_memberships).values(project_id=pid, user_id=96))
    login = client.post("/api/auth/login", headers=ORIGIN,
                        json={"username": "mapping-intent-admin", "password": PASSWORD})
    assert login.status_code == 200, login.text
    headers = ORIGIN | {"X-CSRF-Token": login.json()["csrf_token"]}
    cid = client.post("/api/chat/conversations", headers=headers).json()["id"]
    # Intentionally incomplete header: mapping must remain reviewable, not approved.
    csv = (
        "project_code,activity_code,approved_start_date,unknown_end\n"
        "TCD,26-TCD-021,2026-10-01,2026-10-31\n"
        "FOS,26-FOS-031,2026-10-01,2026-10-31\n"
    )
    upload = client.post("/api/documents", params={
        "filename": "planning.csv", "conversation_id": cid,
    }, content=csv.encode(), headers=headers | {"Content-Type": "text/csv"})
    assert upload.status_code == 201, upload.text

    def send(message):
        response = client.post(f"/api/chat/conversations/{cid}/messages", headers=headers,
                               json={"message": message, "request_id": str(uuid4())})
        assert response.status_code == 200, response.text
        return response.json()["message"]["text"]

    mapping_reply = send("Show me the mapping so I review and approve it")
    assert "Review source mappings" in mapping_reply
    proposal = client.get(f"/api/global-mappings/{cid}")
    assert proposal.status_code == 200, proposal.text
    assert proposal.json()["project_ids"] == [1, 2]
    assert proposal.json()["confirmed"] is False

    followup = send("What do you need from me to continue the workflow?")
    assert "Next step:" in followup and "source mappings" in followup

    # Confirmation and financial authorization must remain explicit.
    from sqlalchemy import text
    with Session(client.app.state.engine) as db:
        assert db.execute(text("SELECT count(*) FROM payment_batches")).scalar() == 0
