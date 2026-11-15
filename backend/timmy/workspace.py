from collections import defaultdict
import re
from secrets import token_urlsafe
from threading import Lock
from time import monotonic, time
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from .audit import audit
from .auth import (
    COOKIE, PERMISSIONS, Authenticated, Database, digest, new_session,
    password_hasher, require_csrf, require_origin, verify_password,
)
from .models import LoginSession, Role, User, activities, imports, payment_policies, project_memberships, projects
from .models import AuditEvent, StoredFile, project_permission_overrides, project_roles, role_permissions, user_roles
from .authorization import CATALOG, DELEGABLE, effective_access
from .repositories import find_user
from .routes import session_view
from .auth import current_principal, principal_for

router = APIRouter(prefix="/api/workspace")
Password = Annotated[str, Field(min_length=12, max_length=1024)]


class AuthLimit:
    def __init__(self):
        self.lock = Lock()
        self.windows: dict[tuple[str, str], list[float]] = defaultdict(list)

    def check(self, request: Request, action: str):
        address = request.client.host if request.client else "local"
        now = monotonic()
        with self.lock:
            self.windows = defaultdict(list, {
                key: values for key, stamps in self.windows.items()
                if (values := [stamp for stamp in stamps if now - stamp < 60])
            })
            stamps = self.windows[address, action]
            if len(stamps) >= 10:
                raise HTTPException(429, "Too many attempts. Try again in a minute.")
            stamps.append(now)


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Account(Payload):
    username: str = Field(min_length=1, max_length=80)
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    middle_name: str | None = Field(default=None, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    email: str | None = Field(default=None, max_length=254)
    extra_roles: list[int] = Field(default_factory=list, max_length=20)
    role: str
    project_ids: list[int] = Field(default_factory=list, max_length=100)
    mode: Literal["temporary", "activation"] = "temporary"


class AccountEdit(Payload):
    role: str
    project_ids: list[int] = Field(max_length=100)
    active: bool


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=1024)
    password: Password


class Activation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=40, max_length=128)
    password: Password


class Mode(Payload):
    mode: Literal["temporary", "activation"]


class ProjectInput(Payload):
    name: str = Field(min_length=1, max_length=160)
    code: str = Field(min_length=1, max_length=80)

    @field_validator('code')
    @classmethod
    def valid_prefix(cls, value):
        if not value[0].isalnum() or any(not c.isalnum() and c not in '-_' for c in value):
            raise ValueError('Project code prefix must use letters, digits, hyphens or underscores')
        return value


class ProjectCreate(ProjectInput):
    policy_family: Literal["session", "hours"]


class ProjectTransition(Payload):
    action: Literal["activate", "complete", "archive", "restore"]


class Activity(Payload):
    name: str = Field(min_length=1, max_length=160)


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Conflicting record or protected dependency") from None


def invalidate(db, user_id):
    db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))


def provision(user, mode, config):
    secret = token_urlsafe(32)
    user.must_change_password = mode == "temporary"
    if mode == "temporary":
        user.active = True
        user.password_hash = password_hasher.hash(secret)
        user.activation_hash = None
        user.activation_expires = None
        return {"temporary_password": secret}
    user.active = False
    user.password_hash = password_hasher.hash(token_urlsafe(32))
    user.activation_hash = digest(secret)
    user.activation_expires = int(time()) + config.activation_minutes * 60
    return {"activation_url": f"{config.frontend_origin}/#activate={secret}"}


def role_id(db, name):
    if name not in PERMISSIONS:
        raise HTTPException(422, "Unknown role")
    role = db.scalar(select(Role).where(Role.name == name))
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role.id


def memberships(db, user_id, identifiers):
    distinct = set(identifiers)
    existing = set(db.scalars(select(projects.c.id).where(projects.c.id.in_(distinct))))
    if distinct != existing:
        raise HTTPException(422, "Unknown project assignment")
    previous = set(db.scalars(select(project_memberships.c.project_id).where(project_memberships.c.user_id == user_id)))
    db.execute(delete(project_memberships).where(project_memberships.c.user_id == user_id,
                                                 project_memberships.c.project_id.in_(previous - distinct)))
    for project_id in sorted(distinct - previous):
        db.execute(insert(project_memberships).values(user_id=user_id, project_id=project_id))


@router.get("/roles")
def roles(principal: Authenticated):
    principal.require("roles:read")
    return {role: sorted(values) for role, values in PERMISSIONS.items()}


@router.get("/users")
def users(principal: Authenticated, db: Database):
    principal.require("users:manage")
    return [
        {"id": user.id, "username": user.username, "role": role, "active": user.active,
         "password_change_required": user.must_change_password, "activation_pending": user.activation_hash is not None,
         "permissions": sorted(effective_access(db, user)[0]),
         "first_name": user.first_name, "middle_name": user.middle_name, "last_name": user.last_name,
         "email": user.email,
         "project_permissions": effective_access(db, user)[1],
         "project_overrides": dict(db.execute(select(
             project_permission_overrides.c.project_id, project_permission_overrides.c.permissions,
         ).where(project_permission_overrides.c.user_id == user.id)).all()),
         "scoped_roles": {
             project_id: list(db.scalars(select(project_roles.c.role_id).where(
                 project_roles.c.user_id == user.id, project_roles.c.project_id == project_id,
             )))
             for project_id in db.scalars(select(project_memberships.c.project_id).where(
                 project_memberships.c.user_id == user.id,
             ))
         },
         "extra_roles": list(db.scalars(select(user_roles.c.role_id).where(user_roles.c.user_id == user.id))),
         "project_ids": list(db.scalars(select(project_memberships.c.project_id)
                                       .where(project_memberships.c.user_id == user.id)))}
        for user, role in db.execute(select(User, Role.name).join(Role).order_by(User.username))
    ]


@router.post("/users", status_code=201)
def create_user(body: Account, request: Request, principal: Authenticated, db: Database):
    principal.require("users:manage")
    require_csrf(request, principal)
    principal = lock_account_edit(db, request)
    if find_user(db, body.username):
        raise HTTPException(409, "Username already exists")
    email = body.email.casefold() if body.email else None
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(422, "Enter a valid email address")
    if email and db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Email already exists")
    user = User(username=body.username, role_id=role_id(db, body.role), email=email,
                first_name=body.first_name, middle_name=body.middle_name, last_name=body.last_name)
    result = provision(user, body.mode, request.app.state.config)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        raise HTTPException(409, "Username already exists") from None
    memberships(db, user.id, body.project_ids)
    set_extra_roles(db, user.id, body.extra_roles)
    audit(db, "user_created", principal.user.id, resource_type="user", resource_id=str(user.id))
    commit(db)
    return result


def lock_account_edit(db, request):
    # Serialize account changes and recheck the current session after taking the write lock.
    db.rollback()
    db.execute(text("BEGIN IMMEDIATE"))
    principal = current_principal(request, db)
    principal.require("users:manage")
    require_csrf(request, principal)
    return principal


def managed_user(db, principal, identifier):
    if identifier == principal.user.id:
        raise HTTPException(409, "Use your own security settings for account changes")
    user = db.get(User, identifier)
    if user is None:
        raise HTTPException(404, "User unavailable")
    return user


@router.patch("/users/{identifier}", status_code=204)
def edit_user(identifier: int, body: AccountEdit, request: Request, principal: Authenticated, db: Database):
    principal.require("users:manage")
    require_csrf(request, principal)
    principal = lock_account_edit(db, request)
    user = managed_user(db, principal, identifier)
    if body.active and user.activation_hash:
        raise HTTPException(409, "Account must complete activation first")
    if not body.active and user.activation_hash:
        user.activation_hash = None
        user.activation_expires = None
    user.active = body.active
    user.role_id = role_id(db, body.role)
    memberships(db, user.id, body.project_ids)
    invalidate(db, user.id)
    audit(db, "user_updated", principal.user.id, resource_type="user", resource_id=str(user.id))
    commit(db)


@router.post("/users/{identifier}/reset")
def reset(identifier: int, body: Mode, request: Request, principal: Authenticated, db: Database):
    principal.require("users:manage")
    require_csrf(request, principal)
    principal = lock_account_edit(db, request)
    user = managed_user(db, principal, identifier)
    result = provision(user, body.mode, request.app.state.config)
    invalidate(db, user.id)
    audit(db, "user_credentials_reset", principal.user.id, resource_type="user", resource_id=str(user.id))
    commit(db)
    return result


@router.post("/activate", status_code=204)
def activate(body: Activation, request: Request, db: Database):
    require_origin(request)
    request.app.state.auth_limit.check(request, "activation")
    token_hash = digest(body.token)
    result = db.execute(update(User).where(
        User.activation_hash == token_hash, User.activation_expires > int(time()), User.active.is_(False),
    ).values(activation_hash=None, activation_expires=None, active=True,
             password_hash=password_hasher.hash(body.password), must_change_password=False).returning(User.id))
    user_id = result.scalar_one_or_none()
    if user_id is None:
        raise HTTPException(400, "Activation link is invalid or expired")
    audit(db, "user_activated", user_id)
    commit(db)


@router.post("/password")
def change_password(body: PasswordChange, request: Request, response: Response, principal: Authenticated, db: Database):
    require_csrf(request, principal)
    request.app.state.auth_limit.check(request, "password")
    user = principal.user
    if not verify_password(user, body.current_password) or body.current_password == body.password:
        raise HTTPException(400, "Enter the current password and choose a different password")
    user.password_hash = password_hasher.hash(body.password)
    user.must_change_password = False
    invalidate(db, user.id)
    config = request.app.state.config
    token, session = new_session(db, user.id, config.session_hours)
    view = session_view(principal_for(db, user, principal.role, session), config.demo_mode)
    audit(db, "password_changed", user.id)
    commit(db)
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=config.cookie_secure,
                        max_age=config.session_hours * 3600, path="/api")
    return view


@router.get("/projects")
def project_list(principal: Authenticated, db: Database):
    principal.require("projects:read")
    query = select(projects.c.id, projects.c.name, projects.c.project_code, projects.c.policy_family, projects.c.status)
    if "projects:manage" not in principal.permissions:
        query = query.where(projects.c.id.in_([key for key, permissions in principal.project_permissions.items() if "projects:read" in permissions]))
    return [dict(row) for row in db.execute(query.order_by(projects.c.name)).mappings()]


def project(db, identifier):
    row = db.execute(select(projects).where(projects.c.id == identifier)).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "Project unavailable")
    return row


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, request: Request, principal: Authenticated, db: Database):
    principal.require("projects:manage")
    require_csrf(request, principal)
    try:
        identifier = db.execute(insert(projects).values(
            name=body.name, project_code=body.code, policy_family=body.policy_family, status="active",
        )).inserted_primary_key[0]
    except IntegrityError:
        raise HTTPException(409, "Project code already exists") from None
    db.execute(insert(project_memberships).values(project_id=identifier, user_id=principal.user.id))
    audit(db, "project_created", principal.user.id, resource_type="project", resource_id=str(identifier))
    commit(db)
    return {"id": identifier}


@router.patch("/projects/{identifier}", status_code=204)
def edit_project(identifier: int, body: ProjectInput, request: Request, principal: Authenticated, db: Database):
    principal.require("projects:manage")
    require_csrf(request, principal)
    db.rollback()
    db.execute(text('BEGIN IMMEDIATE'))
    principal = current_principal(request, db)
    principal.require('projects:manage')
    require_csrf(request, principal)
    row = project(db, identifier)
    if row["status"] == "archived":
        raise HTTPException(409, "Restore the project before editing")
    if body.code != row['project_code'] and db.scalar(select(activities.c.id).where(
            activities.c.project_id==identifier, activities.c.activity_code.is_not(None)).limit(1)):
        raise HTTPException(409,'Project code prefix is permanent once planning activities exist')
    try:
        db.execute(update(projects).where(projects.c.id == identifier, projects.c.status == row["status"])
                   .values(name=body.name, project_code=body.code))
    except IntegrityError:
        raise HTTPException(409, "Project code already exists") from None
    audit(db, "project_updated", principal.user.id, resource_type="project", resource_id=str(identifier))
    commit(db)


@router.post("/projects/{identifier}/transition", status_code=204)
def transition(identifier: int, body: ProjectTransition, request: Request, principal: Authenticated, db: Database):
    principal.require("projects:manage")
    require_csrf(request, principal)
    row = project(db, identifier)
    status = row["status"]
    transitions = {("draft", "activate"): "active", ("active", "complete"): "completed",
                   ("active", "archive"): "archived", ("completed", "archive"): "archived",
                   ("draft", "archive"): "archived", ("archived", "restore"): row["archived_from"]}
    target = transitions.get((status, body.action))
    if not target:
        raise HTTPException(409, "Project transition unavailable")
    result = db.execute(update(projects).where(projects.c.id == identifier, projects.c.status == status)
                        .values(status=target, archived_from=status if target == "archived" else None))
    if result.rowcount != 1:
        raise HTTPException(409, "Project changed. Reload and retry.")
    audit(db, f"project_{body.action}", principal.user.id, resource_type="project", resource_id=str(identifier))
    commit(db)


@router.delete("/projects/{identifier}", status_code=204)
def remove_project(identifier: int, confirmed: bool, request: Request, principal: Authenticated, db: Database):
    principal.require("projects.delete")
    require_csrf(request, principal)
    if not confirmed:
        raise HTTPException(400, "Confirm permanent deletion")
    project(db, identifier)
    for table in (activities, imports, payment_policies, StoredFile.__table__):
        if db.scalar(select(table.c.id).where(table.c.project_id == identifier).limit(1)) is not None:
            raise HTTPException(409, "Project has protected history. Archive it instead.")
    db.execute(delete(project_memberships).where(project_memberships.c.project_id == identifier))
    try:
        db.execute(delete(projects).where(projects.c.id == identifier))
    except IntegrityError:
        raise HTTPException(409, "Project has protected history. Archive it instead.") from None
    audit(db, "project_deleted", principal.user.id, resource_type="project", resource_id=str(identifier))
    commit(db)


@router.get("/activities")
def list_activities(principal: Authenticated, db: Database):
    principal.require("projects:read")
    query = select(activities.c.id, activities.c.name, activities.c.activity_code,
                   activities.c.planned_start, activities.c.planned_end, activities.c.code_authority,
                   projects.c.name.label("project"), projects.c.project_code).join(projects)
    if "projects:manage" not in principal.permissions:
        query = query.where(projects.c.id.in_([key for key, permissions in principal.project_permissions.items() if "activities.view" in permissions]))
    return [dict(row) for row in db.execute(query.order_by(activities.c.id)).mappings()]


@router.post("/projects/{identifier}/activities", status_code=204)
def add_activity(identifier: int, body: Activity, request: Request, principal: Authenticated, db: Database):
    principal.require("projects:manage")
    require_csrf(request, principal)
    raise HTTPException(409,'Activities originate in the planning sheet. Import/process planning to register activity codes; manual name-only creation is unavailable.')


def custom_role(db, identifier):
    role = db.get(Role, identifier)
    if role is None or role.name in PERMISSIONS:
        raise HTTPException(422, "Choose a custom role")
    return role


def set_extra_roles(db, user_id, identifiers):
    db.execute(delete(user_roles).where(user_roles.c.user_id == user_id))
    for identifier in set(identifiers):
        custom_role(db, identifier)
        db.execute(insert(user_roles).values(user_id=user_id, role_id=identifier))


class RoleDefinition(Payload):
    name: str = Field(min_length=1, max_length=40)
    description: str = Field(max_length=240)
    permissions: list[str] = Field(max_length=30)


class AccessAssignment(Payload):
    user_id: int
    role_ids: list[int] = Field(max_length=20)
    project_id: int | None = None


@router.get("/iam/roles")
def role_directory(principal: Authenticated, db: Database):
    principal.require("roles:read")
    return {
        "catalog": CATALOG, "delegable": sorted(DELEGABLE),
        "custom": [
            {"id": role.id, "name": role.name, "description": role.description, "permissions": list(db.scalars(
                select(role_permissions.c.permission).where(role_permissions.c.role_id == role.id)
            )), "assigned_users": len(set(db.scalars(select(user_roles.c.user_id).where(
                user_roles.c.role_id == role.id
            ))) | set(db.scalars(select(project_roles.c.user_id).where(project_roles.c.role_id == role.id))))}
            for role in db.scalars(select(Role).order_by(Role.name)) if role.name not in PERMISSIONS
        ],
    }


@router.post("/iam/roles", status_code=204)
@router.patch("/iam/roles/{identifier}", status_code=204)
def save_role(body: RoleDefinition, request: Request, principal: Authenticated, db: Database,
              identifier: int | None = None):
    principal.require("iam.roles.manage")
    require_csrf(request, principal)
    principal = lock_account_edit(db, request)
    principal.require("iam.roles.manage")
    name = body.name.casefold()
    if name in PERMISSIONS or not set(body.permissions) <= DELEGABLE:
        raise HTTPException(403, "Reserved role or nondelegable permission")
    role = custom_role(db, identifier) if identifier is not None else Role(name=name)
    role.name, role.description = name, body.description
    db.add(role)
    try:
        db.flush()
    except IntegrityError:
        raise HTTPException(409, "Role name already exists") from None
    db.execute(delete(role_permissions).where(role_permissions.c.role_id == role.id))
    for key in sorted(set(body.permissions)):
        db.execute(insert(role_permissions).values(role_id=role.id, permission=key))
    audit(db, "iam_role_saved", principal.user.id, resource_type="role", resource_id=str(role.id),
          trigger="iam", outcome="success")
    commit(db)


@router.put("/iam/assignments", status_code=204)
def assign_access(body: AccessAssignment, request: Request, principal: Authenticated, db: Database):
    principal.require("users:manage")
    require_csrf(request, principal)
    principal = lock_account_edit(db, request)
    user = managed_user(db, principal, body.user_id)
    if body.project_id is None:
        set_extra_roles(db, user.id, body.role_ids)
    else:
        if db.scalar(select(project_memberships.c.user_id).where(
            project_memberships.c.user_id == user.id, project_memberships.c.project_id == body.project_id,
        )) is None:
            raise HTTPException(409, "Assign project membership first")
        db.execute(delete(project_roles).where(project_roles.c.user_id == user.id,
                                               project_roles.c.project_id == body.project_id))
        for identifier in set(body.role_ids):
            custom_role(db, identifier)
            db.execute(insert(project_roles).values(user_id=user.id, project_id=body.project_id, role_id=identifier))
    audit(db, "iam_access_changed", principal.user.id, resource_type="user", resource_id=str(user.id),
          trigger="iam", outcome="success")
    commit(db)


@router.get("/iam/audit")
def access_audit(principal: Authenticated, db: Database):
    principal.require("iam.audit.view")
    return [
        {"id": event.id, "actor_id": event.actor_id, "action": event.action,
         "timestamp": event.occurred_at, "target": event.resource_id, "resource": event.resource_type,
         "outcome": event.outcome}
        for event in db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(200))
    ]


class MemberPermissions(Payload):
    permissions: list[str] | None = Field(max_length=30)


@router.put("/iam/projects/{project_id}/members/{user_id}/permissions", status_code=204)
def set_member_permissions(project_id: int, user_id: int, body: MemberPermissions,
                           request: Request, principal: Authenticated, db: Database):
    principal = lock_account_edit(db, request)
    managed_user(db, principal, user_id)
    if db.scalar(select(project_memberships.c.user_id).where(
        project_memberships.c.project_id == project_id, project_memberships.c.user_id == user_id,
    )) is None:
        raise HTTPException(404, "Project membership unavailable")
    if body.permissions is not None and not set(body.permissions) <= DELEGABLE:
        raise HTTPException(403, "Permission cannot be delegated")
    overrides = project_permission_overrides
    db.execute(delete(overrides).where(overrides.c.project_id == project_id, overrides.c.user_id == user_id))
    if body.permissions is not None:
        db.execute(insert(overrides).values(project_id=project_id, user_id=user_id,
                                            permissions=sorted(set(body.permissions))))
    audit(db, "iam_project_permissions_changed", principal.user.id, trigger="iam",
          resource_type="project_member", resource_id=f"{project_id}:{user_id}", outcome="success")
    commit(db)
