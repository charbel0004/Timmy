"""Central permission catalog and request-time effective access resolution."""

from sqlalchemy import select

from .models import Role, role_permissions, user_roles, project_memberships, project_roles, project_permission_overrides

RESERVED = {
    "admin": frozenset({
        "projects:read", "settings:read", "users:manage", "roles:read",
        "projects:manage", "projects.delete", "iam.audit.view", "iam.roles.manage",
    }),
    "coordinator": frozenset({"projects:read"}),
    "reviewer": frozenset({"projects:read"}),
    "approver": frozenset({"projects:read"}),
    "viewer": frozenset({"projects:read"}),
}
# Financial write permissions remain unavailable until the workflow is authorized.
PROJECT_REVIEW = frozenset({"planning.verify", "staff.verify"})
DELEGABLE = PROJECT_REVIEW | frozenset({
    "projects:read", "activities.view", "timesheets.view", "discrepancies.view", "payments.view",
})
CATALOG = sorted(DELEGABLE | frozenset.union(*RESERVED.values()))


def effective_access(db, user):
    if not user.active or user.must_change_password:
        return frozenset(), {}
    assigned = select(user_roles.c.role_id).where(user_roles.c.user_id == user.id)
    roles = db.execute(select(Role.id, Role.name).where(
        (Role.id == user.role_id) | Role.id.in_(assigned)
    )).all()
    global_keys = set()
    for role_id, name in roles:
        # Only the primary reserved administrator role can administer identities.
        if name != "admin" or role_id == user.role_id:
            global_keys.update(RESERVED.get(name, ()))
            if name in RESERVED:
                global_keys.update(DELEGABLE - PROJECT_REVIEW)
        global_keys.update(key for key in db.scalars(select(role_permissions.c.permission).where(
            role_permissions.c.role_id == role_id,
        )) if key in DELEGABLE)

    # Explicit scoped assignments replace the legacy operational baseline for that project.
    scopes_with_roles = set(db.scalars(select(project_roles.c.project_id).where(project_roles.c.user_id == user.id)))
    scoped = {identifier: set(global_keys & DELEGABLE) if identifier not in scopes_with_roles
              else {"projects:read"} & global_keys for identifier in db.scalars(
        select(project_memberships.c.project_id).where(project_memberships.c.user_id == user.id)
    )}
    query = select(project_roles.c.project_id, role_permissions.c.permission).join(
        role_permissions, role_permissions.c.role_id == project_roles.c.role_id,
    ).where(project_roles.c.user_id == user.id)
    for identifier, key in db.execute(query):
        if identifier in scoped and key in DELEGABLE:
            scoped[identifier].add(key)
    overrides = select(project_permission_overrides.c.project_id, project_permission_overrides.c.permissions).where(
        project_permission_overrides.c.user_id == user.id,
    )
    for identifier, keys in db.execute(overrides):
        if identifier in scoped:
            scoped[identifier] = set(keys) & DELEGABLE
    return frozenset(global_keys), {identifier: sorted(keys) for identifier, keys in scoped.items()}
