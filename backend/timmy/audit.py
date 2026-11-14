from time import time

from sqlalchemy.orm import Session

from .models import AuditEvent


def audit(
    db: Session, action: str, actor_id: int | None = None, *,
    trigger: str | None = None, resource_type: str | None = None,
    resource_id: str | None = None, outcome: str | None = None,
    evidence_file_id: str | None = None,
) -> None:
    db.add(AuditEvent(
        action=action, actor_id=actor_id, occurred_at=int(time()), trigger=trigger,
        resource_type=resource_type, resource_id=resource_id, outcome=outcome,
        evidence_file_id=evidence_file_id,
    ))
