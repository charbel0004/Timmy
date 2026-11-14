from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from timmy.auth import password_hasher
from timmy.config import Settings, settings
from timmy.main import create_app
from timmy.models import AuditEvent, Role, User, project_memberships, projects

ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "local test password"


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("TIMMY_DATABASE_URL", url)
    settings.cache_clear()
    try:
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(config, "head")
        command.check(config)
        with TestClient(create_app(Settings(database_url=url))) as client:
            with Session(client.app.state.engine) as db, db.begin():
                reviewer = Role(name="reviewer")
                unknown = Role(name="unknown")
                db.add_all([reviewer, unknown])
                db.flush()
                password_hash = password_hasher.hash(PASSWORD)
                assert password_hash.startswith("$argon2id$")
                db.add_all([
                    User(id=1, username="reviewer", password_hash=password_hash, role_id=reviewer.id),
                    User(id=2, username="unknown", password_hash=password_hash, role_id=unknown.id),
                ])
                db.flush()
                db.execute(insert(projects), [{"id": 1, "name": "مشروع"}, {"id": 2, "name": "Other"}])
                db.execute(insert(project_memberships).values(project_id=1, user_id=1))
            yield client
    finally:
        settings.cache_clear()


def test_session_and_project_scope(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/projects").status_code == 401
    credentials = {"username": "reviewer", "password": PASSWORD}
    assert client.post("/api/auth/login", json=credentials).status_code == 403
    bad = {**credentials, "password": "wrong"}
    assert client.post("/api/auth/login", headers=ORIGIN, json=bad).status_code == 401
    login = client.post("/api/auth/login", headers=ORIGIN, json=credentials)
    assert login.status_code == 200
    assert "HttpOnly" in login.headers["Set-Cookie"]
    assert "SameSite=strict" in login.headers["Set-Cookie"]
    session = client.get("/api/auth/session")
    assert session.headers["Cache-Control"] == "no-store"
    assert session.json()["role"] == "reviewer"
    assert client.get("/api/projects").json() == [{"id": 1, "name": "مشروع"}]
    assert client.get("/api/settings").status_code == 403
    csrf = {"X-CSRF-Token": session.json()["csrf_token"]}
    assert client.post("/api/auth/logout", headers=csrf).status_code == 403
    assert client.post("/api/auth/logout", headers=ORIGIN).status_code == 403
    assert client.post("/api/auth/logout", headers=ORIGIN | csrf).status_code == 204
    assert client.get("/api/auth/session").status_code == 401
    with Session(client.app.state.engine) as db:
        assert list(db.scalars(select(AuditEvent.action).order_by(AuditEvent.id))) == [
            "login_failed", "login_succeeded", "logout",
        ]


def test_unknown_role_and_cors(client):
    login = client.post("/api/auth/login", headers=ORIGIN, json={
        "username": "unknown", "password": PASSWORD,
    })
    assert login.json()["permissions"] == []
    assert client.get("/api/projects").status_code == 403
    response = client.get("/api/health", headers={"Origin": "https://example.test"})
    assert "Access-Control-Allow-Origin" not in response.headers
    response = client.get("/api/health", headers=ORIGIN)
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN["Origin"]


def test_unmigrated_health(tmp_path):
    with TestClient(create_app(Settings(database_url=f"sqlite:///{tmp_path / 'empty.db'}"))) as client:
        assert client.get("/api/health").status_code == 503


def test_remote_ollama_is_rejected():
    with pytest.raises(ValidationError):
        Settings(ollama_url="https://example.test")


def test_chat_persists_bounded_turns_and_checks_access(client, monkeypatch):
    from uuid import uuid4
    from timmy.ai import OllamaAdapter

    async def structured(self, messages, schema):
        assert len(messages) <= 6
        return schema(answer="مرحباً", tool=None)

    monkeypatch.setattr(OllamaAdapter, "structured", structured)
    url = "/api/chat/conversations"
    assert client.get(url).status_code == 401
    login = client.post("/api/auth/login", headers=ORIGIN, json={
        "username": "reviewer", "password": PASSWORD,
    })
    headers = ORIGIN | {"X-CSRF-Token": login.json()["csrf_token"]}
    assert client.post(url, headers=ORIGIN).status_code == 403
    created = client.post(url, headers=headers)
    assert created.status_code == 201
    conversation = f"{url}/{created.json()['id']}"
    payload = {"request_id": str(uuid4()), "message": "مرحبا"}
    response = client.post(f"{conversation}/messages", headers=headers, json=payload)
    assert response.status_code == 200
    assert response.json()["message"]["text"] == "مرحباً"
    assert client.post(f"{conversation}/messages", headers=headers, json=payload).json() == response.json()
    assert len(client.get(conversation).json()["messages"]) == 2
    renamed = client.patch(conversation, headers=headers, json={"title": "Arabic conversation"})
    assert renamed.json()["title"] == "Arabic conversation"
    assert client.get(url).json()[0]["title"] == "Arabic conversation"
    assert client.delete(conversation, headers=headers).status_code == 204
    assert client.get(conversation).status_code == 404


def test_document_foundation_constraints(client):
    from sqlalchemy.exc import IntegrityError
    from timmy.audit import audit
    from timmy.models import StoredFile

    def evidence(**changes):
        fields = dict(
            purpose="timesheet", original_filename="synthetic.csv",
            relative_storage_key="originals/timesheets/synthetic",
            sha256="a" * 64, size_bytes=12, mime_type="text/csv",
            uploaded_at="2026-11-14T10:00:00Z", project_id=1, uploaded_by=1,
        )
        return StoredFile(**(fields | changes))

    engine = client.app.state.engine
    with Session(engine) as db, db.begin():
        db.execute(insert(projects).values(name="Synthetic project", project_code="SYNTHETIC"))
        file = evidence()
        db.add(file)
        db.flush()
        audit(db, "metadata_created", 1, trigger="test", resource_type="stored_file",
              resource_id=file.id, outcome="recorded", evidence_file_id=file.id)

    for changes in (
        {"project_id": 999, "relative_storage_key": "missing-project"},
        {"relative_storage_key": "invalid-hash", "sha256": "x" * 64},
        {"relative_storage_key": "invalid-size", "size_bytes": 0},
        {},
    ):
        with pytest.raises(IntegrityError), Session(engine) as db, db.begin():
            db.add(evidence(**changes))

    with pytest.raises(IntegrityError), Session(engine) as db, db.begin():
        db.execute(insert(projects).values(name="Duplicate", project_code="SYNTHETIC"))

    with Session(engine) as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == "metadata_created"))
        assert event.trigger == "test"
        assert event.resource_id == event.evidence_file_id
        assert db.get(StoredFile, event.evidence_file_id).original_filename == "synthetic.csv"


def test_operational_records_are_project_scoped(client):
    from timmy.models import discrepancies, imports, timesheets, payment_batches, payment_policies

    with Session(client.app.state.engine) as db, db.begin():
        for identifier in (1, 2):
            db.execute(insert(imports).values(id=identifier, project_id=identifier,
                                             uploaded_by=1, source_name=f"synthetic-{identifier}.csv"))
            db.execute(insert(timesheets).values(id=identifier, import_id=identifier, source_row=2, source_values={}))
            db.execute(insert(discrepancies).values(id=identifier, timesheet_id=identifier, code="REVIEW"))
            db.execute(insert(payment_policies).values(id=identifier, project_id=identifier, version=1))
            db.execute(insert(payment_batches).values(id=identifier, policy_id=identifier))

    client.post("/api/auth/login", headers=ORIGIN, json={"username": "reviewer", "password": PASSWORD})
    for section in ("imports", "timesheets", "discrepancies", "batches"):
        response = client.get(f"/api/operations/{section}")
        assert response.status_code == 200
        assert [row["id"] for row in response.json()] == [1]


def test_workspace_onboarding_and_lifecycle(client):
    with Session(client.app.state.engine) as db, db.begin():
        admin = Role(name="admin")
        db.add(admin)
        db.flush()
        db.add(User(username="admin", password_hash=password_hasher.hash(PASSWORD), role_id=admin.id))

    def login(username, password):
        return client.post("/api/auth/login", headers=ORIGIN,
                           json={"username": username, "password": password})

    def csrf(response):
        assert response.status_code == 200
        return ORIGIN | {"X-CSRF-Token": response.json()["csrf_token"]}

    base = "/api/workspace"
    headers = csrf(login("reviewer", PASSWORD))
    assert client.post(f"{base}/projects", headers=headers, json={"name": "Test", "code": "T"}).status_code == 403
    headers = csrf(login("admin", PASSWORD))
    created = client.post(f"{base}/projects", headers=headers, json={"name": "Test", "code": "T"})
    assert created.status_code == 201
    identifier = created.json()["id"]
    project = f"{base}/projects/{identifier}"
    for action in ("activate", "complete", "archive", "restore"):
        assert client.post(f"{project}/transition", headers=headers, json={"action": action}).status_code == 204
    assert client.delete(f"{base}/projects/2?confirmed=true", headers=headers).status_code == 204
    with Session(client.app.state.engine) as db, db.begin():
        from timmy.models import activities
        db.execute(insert(activities).values(project_id=identifier, name="Protected"))
    assert client.delete(f"{project}?confirmed=true", headers=headers).status_code == 409
    admin_id = next(item["id"] for item in client.get(f"{base}/users").json() if item["username"] == "admin")
    assert client.patch(f"{base}/users/{admin_id}", headers=headers, json={
        "role": "viewer", "active": False, "project_ids": [],
    }).status_code == 409

    pending = client.post(f"{base}/users", headers=headers, json={
        "username": "invited", "role": "viewer", "mode": "activation",
    })
    assert pending.status_code == 201
    token = pending.json()["activation_url"].split("#activate=")[1]
    for status in (204, 400):
        assert client.post(f"{base}/activate", headers=ORIGIN, json={
            "token": token, "password": PASSWORD,
        }).status_code == status

    temporary = client.post(f"{base}/users", headers=headers, json={
        "username": "temporary", "role": "viewer", "project_ids": [identifier],
    })
    assert temporary.status_code == 201
    secret = temporary.json()["temporary_password"]
    login_response = login("temporary", secret)
    restricted = csrf(login_response)
    assert login_response.json()["must_change_password"]
    assert client.get("/api/projects").status_code == 403
    updated = client.post(f"{base}/password", headers=restricted, json={
        "current_password": secret, "password": PASSWORD,
    })
    assert not updated.json()["must_change_password"]
    assert updated.cookies.get("timmy_session") != login_response.cookies.get("timmy_session")
    assert client.get("/api/projects").status_code == 200
    assert login("temporary", secret).status_code == 401


def test_iam_scoped_permission_isolation_and_live_revocation(client):
    from sqlalchemy import delete
    from timmy.models import imports, project_roles, role_permissions

    with Session(client.app.state.engine) as db, db.begin():
        custom = Role(name="timesheet-reader")
        db.add(custom)
        db.flush()
        db.execute(insert(role_permissions).values(role_id=custom.id, permission="timesheets.view"))
        db.execute(insert(project_roles).values(user_id=1, project_id=1, role_id=custom.id))
        for project_id in (1, 2):
            db.execute(insert(imports).values(project_id=project_id, uploaded_by=1, source_name="synthetic.csv"))

    result = client.post("/api/auth/login", headers=ORIGIN, json={
        "username": "reviewer", "password": PASSWORD,
    })
    headers = ORIGIN | {"X-CSRF-Token": result.json()["csrf_token"]}
    assert result.json()["project_permissions"] == {"1": ["projects:read", "timesheets.view"]}
    assert len(client.get("/api/operations/imports").json()) == 1
    assert client.get("/api/workspace/iam/audit").status_code == 403
    assert client.post("/api/workspace/iam/roles", headers=headers, json={
        "name": "elevated", "description": "", "permissions": ["users:manage"],
    }).status_code == 403
    with Session(client.app.state.engine) as db, db.begin():
        db.execute(delete(role_permissions))
    assert client.get("/api/operations/imports").json() == []


def test_member_override_is_local_and_reversible(client):
    with Session(client.app.state.engine) as db, db.begin():
        admin = Role(name="admin")
        db.add(admin)
        db.flush()
        db.add(User(username="scope-admin", role_id=admin.id, password_hash=password_hasher.hash(PASSWORD)))
    def login(username):
        result = client.post("/api/auth/login", headers=ORIGIN, json={"username": username, "password": PASSWORD})
        assert result.status_code == 200
        return ORIGIN | {"X-CSRF-Token": result.json()["csrf_token"]}
    url = "/api/workspace/iam/projects/1/members/1/permissions"
    headers = login("scope-admin")
    assert client.put(url, headers=headers, json={"permissions": ["users:manage"]}).status_code == 403
    assert client.put(url, headers=headers, json={"permissions": []}).status_code == 204
    reviewer = login("reviewer")
    assert client.get("/api/projects").json() == []
    assert client.put(url, headers=reviewer, json={"permissions": None}).status_code == 403
    assert client.put(url, headers=login("scope-admin"), json={"permissions": None}).status_code == 204
    login("reviewer")
    assert [item["id"] for item in client.get("/api/projects").json()] == [1]


def test_voice_requires_session_csrf_and_supported_audio(client, monkeypatch):
    from timmy import voice
    assert client.get("/api/voice/status").status_code == 401
    login = client.post("/api/auth/login", headers=ORIGIN, json={"username": "reviewer", "password": PASSWORD})
    headers = ORIGIN | {"X-CSRF-Token": login.json()["csrf_token"]}
    assert client.post("/api/voice/transcribe", headers=ORIGIN, content=b"audio").status_code == 403
    assert client.post("/api/voice/transcribe", headers=headers, content=b"audio").status_code == 415
    monkeypatch.setattr(voice, "transcribe_audio", lambda *_: {"text": "test", "language": "en"})
    response = client.post("/api/voice/transcribe", headers=headers | {"Content-Type": "audio/webm"}, content=b"mock")
    assert response.json() == {"text": "test", "language": "en"}
    assert client.post("/api/voice/synthesize", headers=headers, json={"text": " "}).status_code == 422


def test_document_persistence_and_project_scope(client, tmp_path):
    import io
    from openpyxl import Workbook

    client.app.state.config.document_root = tmp_path / "private"
    with Session(client.app.state.engine) as db, db.begin():
        admin = Role(name="admin")
        db.add(admin)
        db.flush()
        db.add(User(id=50, username="doc-admin", role_id=admin.id, password_hash=password_hasher.hash(PASSWORD)))
        db.flush()
        db.execute(insert(project_memberships).values(project_id=1, user_id=50))
    login = client.post("/api/auth/login", headers=ORIGIN, json={"username": "doc-admin", "password": PASSWORD})
    headers = ORIGIN | {"X-CSRF-Token": login.json()["csrf_token"]}
    created = client.post("/api/chat/conversations", headers=headers).json()["id"]
    workbook = Workbook()
    workbook.active.append(["Session", "Date"])
    workbook.active.append(["S1", "2026-07-01"])
    out = io.BytesIO()
    workbook.save(out)
    for filename, data, media in (
        ("synthetic.xlsx", out.getvalue(), "application/octet-stream"),
        ("synthetic.csv", b"Session,Date\nS1,2026-07-01\n", "text/csv"),
    ):
        params = {"filename": filename, "project_id": 1, "conversation_id": created}
        response = client.post("/api/documents", params=params, content=data, headers=headers | {"Content-Type": media})
        assert response.status_code == 201, response.text
        file_id = response.json()["id"]
        assert response.json()["status"] == "PARSED_MAPPING_REQUIRED"
        assert client.get(f"/api/documents/{file_id}/download").content == data
    assert len(client.get("/api/documents", params={"conversation_id": created}).json()) == 2
    client.post("/api/auth/login", headers=ORIGIN, json={"username": "unknown", "password": PASSWORD})
    assert client.get("/api/documents").json() == []
    assert client.get(f"/api/documents/{file_id}/download").status_code == 404


def test_uploaded_timesheet_inspection_reads_private_rows_without_model(tmp_path, client, monkeypatch):
    from uuid import uuid4
    from timmy.ai import OllamaAdapter

    async def unexpected_inference(*args, **kwargs):
        raise AssertionError("Explicit document inspection should call the scoped reader directly")

    monkeypatch.setattr(OllamaAdapter, "structured", unexpected_inference)
    client.app.state.config.document_root = tmp_path / "documents"
    with Session(client.app.state.engine) as db, db.begin():
        role = Role(name="admin")
        db.add(role)
        db.flush()
        db.add(User(id=51, username="document-inspector", role_id=role.id, password_hash=password_hasher.hash(PASSWORD)))
        db.flush()
        db.execute(insert(project_memberships).values(project_id=1, user_id=51))
    login = client.post("/api/auth/login", headers=ORIGIN, json={"username": "document-inspector", "password": PASSWORD})
    headers = ORIGIN | {"X-CSRF-Token": login.json()["csrf_token"]}
    conversation = client.post("/api/chat/conversations", headers=headers).json()["id"]
    response = client.post("/api/documents", params={"filename": "test.csv", "project_id": 1, "conversation_id": conversation},
                           content=b"session_number,work_date,volunteer_id\nS1,2026-07-01,PRIVATE-ID\n",
                           headers=headers | {"Content-Type": "text/csv"})
    assert response.status_code == 201
    identifier = response.json()["id"]
    response = client.post(f"/api/chat/conversations/{conversation}/messages", headers=headers,
                           json={"message": "Inspect the uploaded timesheet structure", "request_id": str(uuid4())})
    assert response.status_code == 200
    answer = response.json()["message"]["text"]
    assert identifier in answer and "2 source rows" in answer and "session number" in answer
    assert r"**test\.csv**" in answer
    assert "PRIVATE-ID" not in answer
    with Session(client.app.state.engine) as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "chat_tool_analyze_documents"))
