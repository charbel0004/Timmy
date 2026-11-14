"""Trusted-provider boundary for report synchronization.

Providers are registered by server code. There is no upload or chat route
that can construct authoritative events.
"""
from datetime import datetime
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import audit
from .models import ExternalReportVersion, activities, projects


class ReportEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=200)
    submitted_at: AwareDatetime
    validated_at: AwareDatetime | None = None
    evidence_ref: str = Field(min_length=1, max_length=500)


class ReportProvider(Protocol):
    source: str

    def health(self) -> Literal["ready", "unavailable"]: ...

    def events(self, project_id: int, activity_code: str) -> list[ReportEvent]: ...


def synchronize(engine, provider: ReportProvider, *, project_id: int, activity_code: str, timezone: str):
    """Load events from a registered provider and freeze the first validated version."""
    zone = ZoneInfo(timezone)
    if provider.health() != "ready":
        raise ValueError("Report provider unavailable")
    events = provider.events(project_id, activity_code)
    if len(events) > 500:
        raise ValueError("Too many report versions")
    with engine.connect() as connection, Session(bind=connection) as db:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        activity_id=db.scalar(select(activities.c.id).where(activities.c.project_id==project_id,
                                                           activities.c.activity_code==activity_code,activities.c.code_authority=='source_supplied'))
        if activity_id is None:
            raise ValueError('Activity is not registered from planning; import its planning evidence first')
        query = select(ExternalReportVersion).where(
            ExternalReportVersion.project_id == project_id,
            ExternalReportVersion.activity_code == activity_code,
        )
        current = {row.version: row for row in db.scalars(query)}
        if any(row.activity_id not in (None,activity_id) for row in current.values()):
            raise ValueError('Conflicting planning activity reference in report evidence')
        for row in current.values():
            row.activity_id=activity_id
        authority = {(row.source, row.report_id) for row in current.values()}
        authority.update((provider.source, event.report_id) for event in events)
        if len(authority) > 1:
            raise ValueError("Conflicting external report authority")
        locked = [row for row in current.values() if row.cutoff]
        if len(locked) > 1:
            raise ValueError("Conflicting frozen cutoffs")
        frozen = locked[0].cutoff if locked else None
        validated = sorted(
            (event for event in events if event.validated_at),
            key=lambda event: (event.validated_at, event.version),
        )
        if not frozen and len(validated) > 1 and validated[0].validated_at == validated[1].validated_at:
            raise ValueError("Ambiguous first validation")
        if locked and validated and validated[0].validated_at < datetime.fromisoformat(locked[0].validated_at):
            raise ValueError("Earlier validation conflicts with the frozen cutoff")
        first = validated[0].version if validated and not frozen else None
        if len({event.version for event in events}) != len(events):
            raise ValueError("Duplicate provider versions")
        for event in events:
            submitted = event.submitted_at.isoformat()
            local_date = event.submitted_at.astimezone(zone).date().isoformat()
            validation = event.validated_at.isoformat() if event.validated_at else None
            if event.validated_at and event.validated_at < event.submitted_at:
                raise ValueError("Report validation predates submission")
            row = current.get(event.version)
            if row and (row.submitted_at != submitted or row.local_date != local_date
                        or (row.validated_at and row.validated_at != validation)):
                raise ValueError("Conflicting or stale report version")
            if row and (row.validated_at or not validation):
                continue
            if row is None:
                row = ExternalReportVersion(
                    project_id=project_id, activity_code=activity_code, activity_id=activity_id, source=provider.source,
                    report_id=event.report_id, version=event.version,
                    submitted_at=submitted, local_date=local_date, evidence_ref=event.evidence_ref,
                )
                db.add(row)
            row.validated_at = validation
            row.evidence_ref = event.evidence_ref
            if event.version == first:
                row.cutoff = local_date
                frozen = local_date
            db.flush()
            audit(db, "external_report_synced", resource_type="external_report_version",
                  resource_id=str(row.id), trigger="trusted_provider", outcome="recorded")
        db.flush()
        connection.commit()
    return frozen
