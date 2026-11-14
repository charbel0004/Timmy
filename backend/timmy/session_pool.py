"""Transactionally group eligible credits supplied by the trusted application layer."""
from itertools import groupby

from sqlalchemy.engine import Engine

from .session_compensation import SESSION_CURRENCY, SESSION_GROUP_SIZE, session_compensation


def pool_credits(engine: Engine) -> int:
    with engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        credits = connection.exec_driver_sql("""
            SELECT c.id, c.staff, c.policy, c.version, c.project
            FROM session_trial_credits c
            LEFT JOIN session_trial_group_credits g ON g.credit_id = c.id
            WHERE g.credit_id IS NULL
            ORDER BY c.staff, c.policy, c.version, c.project, c.id
        """).fetchall()
        created = 0
        for key, pool in groupby(credits, lambda row: (row.staff, row.policy, row.version, row.project)):
            ordered = list(pool)
            for index in range(0, len(ordered) - SESSION_GROUP_SIZE + 1, SESSION_GROUP_SIZE):
                group = connection.exec_driver_sql(
                    "INSERT INTO session_trial_groups(staff,policy,version) VALUES(?,?,?)", key[:3],
                ).lastrowid
                connection.exec_driver_sql(
                    "INSERT INTO session_trial_group_credits(credit_id,group_id) VALUES(?,?)",
                    [(credit.id, group) for credit in ordered[index:index + SESSION_GROUP_SIZE]],
                )
                created += 1
        return created


def export_blockers(engine: Engine, group_id: int) -> tuple[str, ...]:
    """Trial groups carry no authoritative allocation or batch approval."""
    with engine.connect() as connection:
        origins = connection.exec_driver_sql("""
            SELECT DISTINCT c.project FROM session_trial_credits c
            JOIN session_trial_group_credits g ON g.credit_id = c.id
            WHERE g.group_id = ?
        """, (group_id,)).all()
    if not origins:
        raise ValueError("Unknown session payment group")
    blockers = ("BATCH_APPROVAL_REQUIRED",)
    return ("ALLOCATION_REVIEW_REQUIRED", *blockers) if len(origins) > 1 else blockers


def cross_project_proposals(engine: Engine) -> list[dict]:
    """Preview unconsumed trial credits without reserving or committing them."""
    import json
    from hashlib import sha256

    with engine.connect() as connection:
        rows = connection.exec_driver_sql("""
            SELECT c.id, c.staff, c.policy, c.version, c.project, c.assignment
            FROM session_trial_credits c
            LEFT JOIN session_trial_group_credits g ON g.credit_id = c.id
            WHERE g.credit_id IS NULL
            ORDER BY c.staff, c.policy, c.version, c.project, c.id
        """).mappings().all()
    proposals = []
    for _, pool in groupby(rows, lambda row: (row["staff"], row["policy"], row["version"])):
        credits = [dict(row) for row in pool]
        for index in range(0, len(credits) - SESSION_GROUP_SIZE + 1, SESSION_GROUP_SIZE):
            members = credits[index:index + SESSION_GROUP_SIZE]
            if len({member["project"] for member in members}) < 2:
                continue
            amount, _ = session_compensation(len(members))
            data = {"credits": members, "amount": str(amount), "currency": SESSION_CURRENCY}
            digest = sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
            proposals.append({**data, "digest": digest, "status": "CROSS_PROJECT_APPROVAL_MISSING"})
    return proposals
