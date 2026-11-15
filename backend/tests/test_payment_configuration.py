"""Fixed policy-family assignment; no user-defined monetary rules."""
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from test_foundation import ORIGIN, PASSWORD, client
from timmy.auth import password_hasher
from timmy.models import Role, User, payment_policies, projects


def login_admin(client):
    with Session(client.app.state.engine) as db, db.begin():
        role = Role(name="admin")
        db.add(role)
        db.flush()
        db.add(User(username="policy-admin", password_hash=password_hasher.hash(PASSWORD), role_id=role.id))
    response = client.post("/api/auth/login", headers=ORIGIN, json={
        "username": "policy-admin", "password": PASSWORD,
    })
    assert response.status_code == 200
    return ORIGIN | {"X-CSRF-Token": response.json()["csrf_token"]}


def test_project_requires_one_fixed_family_and_rejects_configurable_values(client):
    headers = login_admin(client)
    path = "/api/workspace/projects"
    assert client.post(path, headers=headers, json={
        "name": "No policy", "code": "NOP",
    }).status_code == 422
    assert client.post(path, headers=headers, json={
        "name": "Bad policy", "code": "BAD", "policy_family": "per-project",
    }).status_code == 422
    assert client.post(path, headers=headers, json={
        "name": "Extra configuration", "code": "EXTRA", "policy_family": "session",
        "payment_policy": {"rate": "100.00", "currency": "USD"},
    }).status_code == 422

    for family in ("session", "hours"):
        response = client.post(path, headers=headers, json={
            "name": f"Fixed {family}", "code": family.upper(), "policy_family": family,
        })
        assert response.status_code == 201, response.text
        identifier = response.json()["id"]
        value = client.get(f"/api/payment-policies/{identifier}").json()
        assert value["family"] == family
        assert value["configuration_editable"] is False
        assert value["status"] == ("fixed_session_contract" if family == "session"
                                   else "pending_hourly_contract")
        assert client.post(f"/api/payment-policies/{identifier}", headers=headers,
                           json={"rate": "100"}).status_code == 405
        assert client.post(f"/api/payment-policies/{identifier}/example", headers=headers,
                           json={"rate": "100"}).status_code == 405
        with Session(client.app.state.engine) as db:
            assert db.scalar(select(projects.c.policy_family).where(projects.c.id == identifier)) == family
            assert db.scalar(select(payment_policies.c.id).where(
                payment_policies.c.project_id == identifier
            )) is None


def test_fixed_policy_lookup_does_not_invent_hourly_rate(client):
    headers = login_admin(client)
    created = client.post("/api/workspace/projects", headers=headers, json={
        "name": "Hours", "code": "HRS", "policy_family": "hours",
    })
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    conversation = client.post("/api/chat/conversations", headers=headers).json()["id"]
    result = client.post(f"/api/chat/conversations/{conversation}/messages", headers=headers, json={
        "message": "What is the hourly rate?",
        "request_id": str(uuid4()),
        "project_id": project_id,
    })
    assert result.status_code == 200, result.text
    assert "awaiting explicit approval" in result.json()["message"]["text"]


def test_existing_projects_preserved_without_invented_family(client):
    headers = login_admin(client)
    # The fixture contains historical projects created before this new mandatory choice.
    legacy = client.get("/api/payment-policies/1")
    assert legacy.status_code == 200
    assert legacy.json() == {
        "family": None, "configuration_editable": False, "status": "unassigned_legacy",
    }
