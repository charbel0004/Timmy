from .ai_status import OllamaStatus, probe_ollama
from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .audit import audit
from .auth import (
    COOKIE, Authenticated, Database, Principal, principal_for, digest, new_session, require_csrf,
    require_origin, verify_password,
)
from .models import LoginSession, Role
from .repositories import find_user, visible_projects
from .schemas import Credentials, ProjectView, SessionView

router = APIRouter(prefix="/api")


def session_view(principal: Principal, demo_mode: bool) -> SessionView:
    return SessionView(
        username=principal.user.username, role=principal.role,
        project_permissions=principal.project_permissions,
        permissions=sorted(principal.permissions), csrf_token=principal.session.csrf_token,
        demo_mode=demo_mode, must_change_password=principal.user.must_change_password,
    )


@router.get("/live")
def live():
    return {"status": "ok"}


@router.get("/health")
def health(db: Database):
    try:
        db.execute(text("SELECT version_num FROM alembic_version WHERE version_num = '0017'")).scalar_one()
    except SQLAlchemyError:
        raise HTTPException(503, "Database unavailable or migrations pending") from None
    return {"status": "ok"}


@router.post("/auth/login")
def login(body: Credentials, request: Request, response: Response, db: Database) -> SessionView:
    require_origin(request)
    request.app.state.auth_limit.check(request, "login")
    user = find_user(db, body.username)
    if not verify_password(user, body.password) or user is None or not user.active:
        audit(db, "login_failed")
        db.commit()
        raise HTTPException(401, "Invalid credentials")

    previous_token = request.cookies.get(COOKIE)
    previous = db.get(LoginSession, digest(previous_token)) if previous_token else None
    if previous:
        db.delete(previous)

    config = request.app.state.config
    role = db.get(Role, user.role_id)
    token, session = new_session(db, user.id, config.session_hours)
    view = session_view(principal_for(db, user, role.name, session), config.demo_mode)
    audit(db, "login_succeeded", user.id)
    db.commit()
    response.set_cookie(
        COOKIE, token, httponly=True, samesite="strict", secure=config.cookie_secure,
        max_age=config.session_hours * 3600, path="/api",
    )
    return view


@router.get("/auth/session")
def get_session(request: Request, principal: Authenticated) -> SessionView:
    return session_view(principal, request.app.state.config.demo_mode)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, principal: Authenticated, db: Database) -> Response:
    require_csrf(request, principal)
    audit(db, "logout", principal.user.id)
    db.delete(principal.session)
    db.commit()
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path="/api")
    return response


@router.get("/projects")
def list_projects(principal: Authenticated, db: Database) -> list[ProjectView]:
    principal.require("projects:read")
    return visible_projects(db, principal.user.id)


@router.get("/settings")
def read_settings(request: Request, principal: Authenticated):
    principal.require("settings:read")
    config = request.app.state.config
    return {
        "demo_mode": config.demo_mode, "ollama_model": config.ollama_model,
        "report_integration": {
            "status": "blocked",
            "missing": [
                *(["Approved external source identity"] if not config.report_source else []),
                *(["Approved project timezone"] if not config.report_timezone else []),
                "Registered trusted provider and validated-version mapping",
            ],
        },
    }


@router.get("/ai/status")
async def ai_status(request: Request, principal: Authenticated) -> OllamaStatus:
    principal.require("projects:read")
    config = request.app.state.config
    return await probe_ollama(config)
