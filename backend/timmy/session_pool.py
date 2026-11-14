"""Transactionally group eligible credits supplied by the trusted application layer."""
from itertools import groupby

from sqlalchemy.engine import Engine


def pool_credits(engine: Engine) -> int:
    with engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        credits = connection.exec_driver_sql("""
            SELECT c.id, c.staff, c.policy, c.version
            FROM session_trial_credits c
            LEFT JOIN session_trial_group_credits g ON g.credit_id = c.id
            WHERE g.credit_id IS NULL
            ORDER BY c.staff, c.policy, c.version, c.id
        """).fetchall()
        created = 0
        for key, pool in groupby(credits, lambda row: (row.staff, row.policy, row.version)):
            ordered = list(pool)
            for index in range(0, len(ordered) - 2, 3):
                group = connection.exec_driver_sql(
                    "INSERT INTO session_trial_groups(staff,policy,version) VALUES(?,?,?)", key,
                ).lastrowid
                connection.exec_driver_sql(
                    "INSERT INTO session_trial_group_credits(credit_id,group_id) VALUES(?,?)",
                    [(credit.id, group) for credit in ordered[index:index + 3]],
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
