from uuid import uuid4

from sqlalchemy import CheckConstraint, Column, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, Table, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

metadata = Base.metadata


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    description: Mapped[str | None] = mapped_column(String(240))


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    first_name: Mapped[str | None] = mapped_column(String(80))
    middle_name: Mapped[str | None] = mapped_column(String(80))
    last_name: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)
    active: Mapped[bool] = mapped_column(default=True)
    must_change_password: Mapped[bool] = mapped_column(default=False, server_default="0")
    activation_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    activation_expires: Mapped[int | None]


class LoginSession(Base):
    __tablename__ = "login_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[int] = mapped_column(index=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    occurred_at: Mapped[int] = mapped_column(index=True)
    trigger: Mapped[str | None] = mapped_column(String(80))
    resource_type: Mapped[str | None] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(128))
    outcome: Mapped[str | None] = mapped_column(String(40))
    evidence_file_id: Mapped[str | None] = mapped_column(ForeignKey("stored_files.id"), index=True)


def identity():
    return Column("id", Integer, primary_key=True)


def reference(name, target):
    return Column(name, Integer, ForeignKey(target), nullable=False, index=True)


projects = Table(
    "projects", metadata, identity(), Column("name", String(160), nullable=False),
    Column("project_code", String(80), unique=True, index=True),
    Column("status", String(12), nullable=False, server_default="active"),
    Column("archived_from", String(12)),
    CheckConstraint("status IN ('draft','active','completed','archived')", name="ck_project_status"),
)


class StoredFile(Base):
    __tablename__ = "stored_files"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_stored_files_positive_size"),
        CheckConstraint("length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'", name="ck_stored_files_sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    purpose: Mapped[str] = mapped_column(String(80))
    original_filename: Mapped[str] = mapped_column(Text)
    relative_storage_key: Mapped[str] = mapped_column(Text, unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int]
    mime_type: Mapped[str] = mapped_column(String(128))
    uploaded_at: Mapped[str] = mapped_column(String(32))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
project_memberships = Table(
    "project_memberships", metadata,
    Column("project_id", ForeignKey("projects.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True, index=True),
)
activities = Table(
    "activities", metadata, identity(), reference("project_id", "projects.id"),
    Column("name", String(160), nullable=False),
    Column("activity_code", String(88)),
    Column("planned_start", String(10)), Column("planned_end", String(10)),
    Column('code_authority', String(30), nullable=False, server_default='legacy_review_required'),
    Column('planning_contract_version', String(80)),
)
Index('uq_activities_project_activity_code', activities.c.project_id, activities.c.activity_code, unique=True)
Index('uq_activities_global_code', activities.c.activity_code, unique=True)


class PlanningCodeContract(Base):
    __tablename__ = 'planning_code_contracts'
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id'), primary_key=True)
    version: Mapped[str] = mapped_column(String(80))
    code_pattern: Mapped[str] = mapped_column(String(128))
    source_ref: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    approved_at: Mapped[int]

activity_planning_sources = Table(
    'activity_planning_sources', metadata, identity(), reference('activity_id', 'activities.id'),
    reference('project_id', 'projects.id'),
    Column('file_id', ForeignKey('stored_files.id'), nullable=False),
    Column('source_sha256', String(64), nullable=False),
    Column('sheet_index', Integer, nullable=False), Column('source_row', Integer, nullable=False),
    Column('mapping_id', ForeignKey('mapping_proposals.id'), nullable=False),
    UniqueConstraint('project_id', 'source_sha256', 'sheet_index', 'source_row'),
)
imports = Table(
    "imports", metadata, identity(), reference("project_id", "projects.id"),
    reference("uploaded_by", "users.id"), Column("source_name", Text, nullable=False),
)
timesheets = Table(
    "timesheets", metadata, identity(), reference("import_id", "imports.id"),
    Column("source_row", Integer, nullable=False), Column("source_values", JSON, nullable=False),
    CheckConstraint("source_row > 0"), UniqueConstraint("import_id", "source_row"),
)
discrepancies = Table(
    "discrepancies", metadata, identity(), reference("timesheet_id", "timesheets.id"),
    Column("code", String(80), nullable=False),
)
payment_policies = Table(
    "payment_policies", metadata, identity(), reference("project_id", "projects.id"),
    Column("version", Integer, nullable=False), CheckConstraint("version > 0"),
    UniqueConstraint("project_id", "version"),
    Column("configuration", JSON),
    Column("status", String(16), nullable=False, server_default="draft"),
    Column("created_by", ForeignKey("users.id")),
    Column("created_at", Integer),
    Column("activated_by", ForeignKey("users.id")),
    Column("activated_at", Integer),
)
payment_batches = Table(
    "payment_batches", metadata, identity(), reference("policy_id", "payment_policies.id"),
)
payment_lines = Table(
    "payment_lines", metadata, identity(), reference("batch_id", "payment_batches.id"),
)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(120))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workflow_state: Mapped[dict | None] = mapped_column(JSON)


class MappingProposal(Base):
    __tablename__ = "mapping_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    version: Mapped[int]
    sheets: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    created_at: Mapped[int]
    confirmed_at: Mapped[int | None]
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class ChatTurn(Base):
    __tablename__ = "chat_turns"
    __table_args__ = (UniqueConstraint("conversation_id", "request_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True,
    )
    request_id: Mapped[str] = mapped_column(String(36))
    prompt: Mapped[str] = mapped_column(Text)
    reply: Mapped[str] = mapped_column(Text)
    created_at: Mapped[int]
    context: Mapped[dict | None] = mapped_column(JSON)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (UniqueConstraint("actor_id", "request_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    request_key: Mapped[str] = mapped_column(String(160))
    fingerprint: Mapped[str] = mapped_column(String(64))
    workflow_id: Mapped[str] = mapped_column(String(80))
    knowledge_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[int]
    status: Mapped[str] = mapped_column(String(30))
    snapshot: Mapped[dict] = mapped_column(JSON)




class WorkflowStepReceipt(Base):
    """Immutable outcome record for a committed workflow run.

    All protected activity, planning and source changes still commit in the same
    caller transaction. This table does not claim an independent pre-invocation
    crash checkpoint for future external side effects.
    """
    __tablename__ = "workflow_step_receipts"
    __table_args__ = (
        UniqueConstraint("run_id", "step_index"),
        CheckConstraint("step_index >= 0", name="ck_workflow_step_index"),
        CheckConstraint("status IN ('completed','needs_review','blocked','failed')",
                        name="ck_workflow_step_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    step_index: Mapped[int]
    step_id: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30))
    attempted: Mapped[bool]
    executed: Mapped[bool]
    blocked_by: Mapped[str | None] = mapped_column(String(80))
    issue_codes: Mapped[list] = mapped_column(JSON)
    recorded_at: Mapped[int]

user_roles = Table(
    "user_roles", metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("role_id", ForeignKey("roles.id"), primary_key=True, index=True),
)
role_permissions = Table(
    "role_permissions", metadata,
    Column("role_id", ForeignKey("roles.id"), primary_key=True),
    Column("permission", String(80), primary_key=True),
)
project_roles = Table(
    "project_roles", metadata,
    Column("user_id", Integer, primary_key=True),
    Column("project_id", Integer, primary_key=True, index=True),
    Column("role_id", ForeignKey("roles.id"), primary_key=True, index=True),
    ForeignKeyConstraint(
        ["project_id", "user_id"], ["project_memberships.project_id", "project_memberships.user_id"],
        ondelete="CASCADE",
    ),
)


project_permission_overrides = Table(
    "project_permission_overrides", metadata,
    Column("project_id", Integer, primary_key=True),
    Column("user_id", Integer, primary_key=True),
    Column("permissions", JSON, nullable=False),
    ForeignKeyConstraint(
        ["project_id", "user_id"], ["project_memberships.project_id", "project_memberships.user_id"],
        ondelete="CASCADE",
    ),
)


class DocumentImport(Base):
    __tablename__ = "document_imports"

    file_id: Mapped[str] = mapped_column(ForeignKey("stored_files.id"), primary_key=True)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True,
    )
    sheets: Mapped[list] = mapped_column(JSON)
    row_count: Mapped[int]


class StructuralValidation(Base):
    __tablename__ = "structural_validations"
    __table_args__ = (UniqueConstraint("project_id", "fingerprint"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[int]
    snapshot: Mapped[dict] = mapped_column(JSON)


class EvidenceReview(Base):
    __tablename__ = "evidence_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    validation_id: Mapped[int] = mapped_column(ForeignKey("structural_validations.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    project_code: Mapped[str] = mapped_column(Text)
    activity_code: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16))
    decision: Mapped[str] = mapped_column(String(16))
    evidence_ref: Mapped[str] = mapped_column(Text)
    created_at: Mapped[int]


class ExternalReportVersion(Base):
    __tablename__ = "external_report_versions"
    __table_args__ = (UniqueConstraint("project_id", "activity_code", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    activity_id: Mapped[int | None] = mapped_column(ForeignKey('activities.id'))
    activity_code: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    report_id: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[str] = mapped_column(Text)
    local_date: Mapped[str] = mapped_column(Text)
    validated_at: Mapped[str | None] = mapped_column(Text)
    evidence_ref: Mapped[str] = mapped_column(Text)
    cutoff: Mapped[str | None] = mapped_column(Text)
