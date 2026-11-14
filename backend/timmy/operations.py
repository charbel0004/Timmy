from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from .auth import Authenticated, Database
from .models import (
    discrepancies, imports, payment_batches, payment_policies,
    project_memberships, projects, timesheets,
)

router = APIRouter(prefix="/api/operations")
Section = Literal["imports", "timesheets", "discrepancies", "batches"]


class Record(BaseModel):
    id: int
    project: str
    reference: str
    source_row: int | None = None


@router.get("/{section}")
def records(section: Section, principal: Authenticated, db: Database) -> list[Record]:
    permission = {"imports": "timesheets.view", "timesheets": "timesheets.view",
                  "discrepancies": "discrepancies.view", "batches": "payments.view"}[section]
    if not principal.permissions and not principal.project_permissions:
        principal.require("projects:read")
    permitted_projects = [identifier for identifier, keys in principal.project_permissions.items()
                          if permission in keys]
    project = projects.c.name.label("project")
    if section == "batches":
        query = select(payment_batches.c.id, project, payment_policies.c.version.label("reference")).select_from(
            payment_batches.join(payment_policies).join(projects)
        )
    else:
        query = select(imports.c.id, project, imports.c.source_name.label("reference")).select_from(
            imports.join(projects)
        )
        if section == "timesheets":
            query = query.join(timesheets).with_only_columns(
                timesheets.c.id, project, imports.c.source_name.label("reference"), timesheets.c.source_row,
            )
        elif section == "discrepancies":
            query = query.join(timesheets).join(discrepancies).with_only_columns(
                discrepancies.c.id, project, discrepancies.c.code.label("reference"), timesheets.c.source_row,
            )

    query = query.join(project_memberships, project_memberships.c.project_id == projects.c.id)
    query = query.where(project_memberships.c.user_id == principal.user.id, projects.c.id.in_(permitted_projects))
    query = query.order_by(query.selected_columns.id.desc()).limit(100)
    return [
        Record(id=row.id, project=row.project, reference=str(row.reference),
               source_row=getattr(row, "source_row", None))
        for row in db.execute(query)
    ]
