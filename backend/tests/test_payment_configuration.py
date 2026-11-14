from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from test_foundation import ORIGIN, PASSWORD, client
from timmy.auth import password_hasher
from timmy.models import Role, User

POLICY = {
    "family": "hours", "rate": "17.45", "currency": "USD", "start": "2026-07-01",
    "precision": 2, "monetary_rounding": "half_up", "eligibility": "approved_evidence_only",
    "duration_rounding": "exact", "overnight": "continuous", "daily_cap": 480,
}


def test_versions_preview_activation_and_historical_rate(client):
    with Session(client.app.state.engine) as db, db.begin():
        role = Role(name="admin")
        db.add(role)
        db.flush()
        db.add(User(username="policy-admin", password_hash=password_hasher.hash(PASSWORD), role_id=role.id))
    response = client.post("/api/auth/login", headers=ORIGIN, json={"username": "policy-admin", "password": PASSWORD})
    headers = ORIGIN | {"X-CSRF-Token": response.json()["csrf_token"]}
    created = client.post("/api/workspace/projects", headers=headers,
                          json={"name": "Policy project", "code": "POLICY", "payment_policy": POLICY})
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    path = f"/api/payment-policies/{project_id}"
    v1, = client.get(path).json()
    assert v1["status"] == "draft"
    assert client.get("/api/payment-policies/1").status_code == 403
    example = client.post(f"{path}/example", headers=headers, json=POLICY)
    assert Decimal(example.json()["amount"]) == Decimal("26.18")
    assert client.post(path, headers=headers, json={**POLICY, "overnight": None}).status_code == 422

    activate = f"{path}/{v1['id']}/activate"
    assert client.post(activate, headers=headers, json={"confirmed": False}).status_code == 422
    assert client.post(activate, headers=headers, json={"confirmed": True}).status_code == 200
    v2 = client.post(path, headers=headers, json={**POLICY, "rate": "21.00"}).json()["id"]
    assert client.post(f"{path}/{v2}/activate", headers=headers, json={"confirmed": True}).status_code == 409
    assert client.post(f"{path}/{v2}/activate", headers=headers,
                       json={"confirmed": True, "supersede_policy_id": v1["id"]}).status_code == 200
    active, historical = client.get(path).json()
    assert active["status"] == "active"
    assert historical["status"] == "superseded" and historical["configuration"]["rate"] == "17.45"

    conversation = client.post("/api/chat/conversations", headers=headers).json()["id"]
    result = client.post(f"/api/chat/conversations/{conversation}/messages", headers=headers, json={
        "message": "What is the hourly rate?", "request_id": str(uuid4()), "project_id": project_id,
    })
    assert "USD 21.00 per hour" in result.json()["message"]["text"]
