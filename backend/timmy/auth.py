from collections.abc import Iterator
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
from secrets import token_urlsafe
from time import time
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete
from sqlalchemy.orm import Session

from .authorization import RESERVED as PERMISSIONS, effective_access
from .models import LoginSession, Role, User

COOKIE = "timmy_session"
password_hasher = PasswordHasher()
dummy_hash = password_hasher.hash(token_urlsafe())


def verify_password(user: User | None, password: str) -> bool:
    try:
        return password_hasher.verify(user.password_hash if user else dummy_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def get_db(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as db:
        yield db


Database = Annotated[Session, Depends(get_db)]


def digest(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def new_session(db: Session, user_id: int, hours: int) -> tuple[str, LoginSession]:
    now = int(time())
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= now))
    token = token_urlsafe(32)
    session = LoginSession(
        token_hash=digest(token), csrf_token=token_urlsafe(32),
        user_id=user_id, expires_at=now + hours * 3600,
    )
    db.add(session)
    return token, session


@dataclass(frozen=True)
class Principal:
    user: User
    role: str
    session: LoginSession

    permissions: frozenset[str]
    project_permissions: dict[int, list[str]]

    def require(self, permission: str, project_id: int | None = None) -> None:
        keys = self.permissions if project_id is None else self.project_permissions.get(project_id, ())
        if permission not in keys:
            raise HTTPException(403, "Permission denied")


def principal_for(db, user, role, session):
    permissions, scoped = effective_access(db, user)
    return Principal(user, role, session, permissions, scoped)


def current_principal(request: Request, db: Database) -> Principal:
    token = request.cookies.get(COOKIE)
    session = db.get(LoginSession, digest(token)) if token else None
    if session is None or session.expires_at <= int(time()):
        raise HTTPException(401, "Authentication required")
    user = db.get(User, session.user_id)
    role = db.get(Role, user.role_id) if user and user.active else None
    if role is None or user is None:
        raise HTTPException(401, "Authentication required")
    return principal_for(db, user, role.name, session)


Authenticated = Annotated[Principal, Depends(current_principal)]


def require_origin(request: Request) -> None:
    if request.headers.get("origin") != request.app.state.config.frontend_origin:
        raise HTTPException(403, "Origin denied")


def require_csrf(request: Request, principal: Principal) -> None:
    require_origin(request)
    token = request.headers.get("x-csrf-token", "").encode()
    if not compare_digest(token, principal.session.csrf_token.encode()):
        raise HTTPException(403, "Invalid CSRF token")
