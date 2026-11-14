from sqlalchemy import select
from sqlalchemy.orm import Session

from .authorization import effective_access
from .models import User, project_memberships, projects
from .schemas import ProjectView


def find_user(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def visible_projects(db: Session, user_id: int) -> list[ProjectView]:
    user = db.get(User, user_id)
    if user is None:
        return []
    _, scoped = effective_access(db, user)
    allowed = [identifier for identifier, keys in scoped.items() if "projects:read" in keys]
    query = (
        select(projects.c.id, projects.c.name)
        .join(project_memberships)
        .where(project_memberships.c.user_id == user_id, projects.c.status == "active", projects.c.id.in_(allowed))
        .order_by(projects.c.id)
    )
    return [ProjectView(id=row.id, name=row.name) for row in db.execute(query)]
