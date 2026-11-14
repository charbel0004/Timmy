"""Persistent session evidence and entitlement trial."""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = depends_on = None

DDL = (
    """CREATE TABLE session_trial_sources (
        name TEXT PRIMARY KEY, digest TEXT NOT NULL, payload BLOB NOT NULL)""",
    """CREATE TABLE session_trial_claims (
        id INTEGER PRIMARY KEY, source TEXT NOT NULL REFERENCES session_trial_sources(name),
        row_number INTEGER NOT NULL, project TEXT NOT NULL, activity TEXT NOT NULL,
        UNIQUE(source, row_number))""",
    """CREATE TABLE session_trial_occurrences (
        project TEXT NOT NULL, activity TEXT NOT NULL, number INTEGER NOT NULL CHECK(number BETWEEN 1 AND 6),
        work_date TEXT NOT NULL, PRIMARY KEY(project, activity, number))""",
    """CREATE TABLE session_trial_assignments (
        id INTEGER PRIMARY KEY, project TEXT NOT NULL, activity TEXT NOT NULL, number INTEGER NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('TRAINER','LOGISTIC')), staff TEXT NOT NULL,
        claim_id INTEGER NOT NULL UNIQUE REFERENCES session_trial_claims(id),
        FOREIGN KEY(project,activity,number) REFERENCES session_trial_occurrences(project,activity,number),
        UNIQUE(project,activity,number,role), UNIQUE(project,activity,number,staff))""",
    """CREATE TABLE session_trial_reports (
        project TEXT NOT NULL, activity TEXT NOT NULL, report TEXT NOT NULL, version TEXT NOT NULL,
        submitted TEXT NOT NULL, PRIMARY KEY(project,activity,version))""",
    """CREATE TABLE session_trial_cutoffs (
        project TEXT NOT NULL, activity TEXT NOT NULL, version TEXT NOT NULL, evidence TEXT NOT NULL,
        PRIMARY KEY(project,activity),
        FOREIGN KEY(project,activity,version) REFERENCES session_trial_reports(project,activity,version))""",
    """CREATE TABLE session_trial_credits (
        id TEXT PRIMARY KEY, staff TEXT NOT NULL, policy TEXT NOT NULL, version TEXT NOT NULL,
        project TEXT NOT NULL, assignment INTEGER UNIQUE REFERENCES session_trial_assignments(id))""",
    """CREATE TABLE session_trial_groups (
        id INTEGER PRIMARY KEY, staff TEXT NOT NULL, policy TEXT NOT NULL, version TEXT NOT NULL,
        amount TEXT NOT NULL DEFAULT '25.00' CHECK(amount = '25.00'),
        currency TEXT NOT NULL DEFAULT 'USD' CHECK(currency = 'USD'))""",
    """CREATE TABLE session_trial_group_credits (
        credit_id TEXT PRIMARY KEY REFERENCES session_trial_credits(id),
        group_id INTEGER NOT NULL REFERENCES session_trial_groups(id))""",
)

def upgrade():
    for statement in DDL:
        op.execute(statement)


def downgrade():
    raise RuntimeError("Session evidence migration is forward-only")
