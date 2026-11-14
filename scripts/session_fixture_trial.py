"""Run the supplied synthetic pack in a fresh temporary SQLite database."""
import csv
import hashlib
import io
import json
import os
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from alembic.config import Config

from timmy.config import settings
from timmy.database import make_engine
from timmy.session_pool import export_blockers, pool_credits
from timmy.session_rules import Claim, coverage


def read(directory, name):
    data = (directory / f"{name}.csv").read_bytes()
    if not data or len(data) > 2_000_000 or b"\0" in data:
        raise ValueError(f"Invalid fixture: {name}")
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
    rows = list(reader)
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or len(rows) > 10000:
        raise ValueError(f"Invalid fixture schema: {name}")
    if any(None in row or None in row.values() for row in rows):
        raise ValueError(f"Invalid fixture row: {name}")
    return data, rows


def trial(directory, url):
    os.environ["TIMMY_DATABASE_URL"] = url
    settings.cache_clear()
    command.upgrade(Config("backend/alembic.ini"), "head")
    engine = make_engine(url)
    activity_states = {}
    invalid = {}
    with engine.begin() as db:
        def load(name):
            data, rows = read(directory, name)
            db.exec_driver_sql("INSERT INTO session_trial_sources VALUES(?,?,?)",
                               (name, hashlib.sha256(data).hexdigest(), data))
            return rows

        staged = load("original_timesheets_staging")
        load("original_rate_policies_review")
        load("original_volunteer_directory_staging")
        assert len(staged) == 30
        assert all(row["eligibility_status"] == "BLOCKED_PENDING_EVIDENCE"
                   and not row["claimed_session_number"] and not row["timesheet_submitted_date"] for row in staged)
        staff = {row["staff_id"] for row in load("staff_directory")
                 if row["status"] == "Active" and row["staff_id"].startswith("TEST-")}
        plans = {(row["project_code"], row["activity_code"]): row for row in load("planning_activities")
                 if row["source_authority"] == "SYNTHETIC_TEST_PLANNING"}
        projects = {row["project_code"]: row["policy_id"] for row in load("projects")}
        policies = {row["policy_id"] for row in load("session_policy_test_config")
                    if tuple(row[key] for key in ("approval_source", "family", "required_sessions", "roles",
                                                  "day_patterns", "group_size", "group_amount_usd", "currency"))
                    == ("TEST_HARNESS_ONLY", "session", "6", "TRAINER|LOGISTIC", "3+3|2+2+2", "3", "25.00", "USD")}
        assert all(plan["policy_id"] in policies and plan["policy_id"] == projects[project]
                   for (project, _), plan in plans.items())
        plan_ids = {activity: (project, activity) for project, activity in plans}
        reports = {}
        for row in load("report_events"):
            assert row["source_authority"] == "SYNTHETIC_TRUSTED_TEST_ADAPTER"
            key = plan_ids[row["activity_code"]]
            report = reports.setdefault(key, row["report_id"])
            assert report == row["report_id"]
            if row["event_type"] in {"SUBMITTED", "RESUBMITTED"}:
                db.exec_driver_sql("INSERT INTO session_trial_reports VALUES(?,?,?,?,?)",
                                   (*key, report, row["submission_version_id"], row["submitted_local_date"]))
            elif row["event_type"] == "VALIDATED":
                version = row["validated_submission_version_id"]
                assert db.exec_driver_sql("SELECT 1 FROM session_trial_reports WHERE project=? AND activity=? AND version=?",
                                          (*key, version)).first()
                db.exec_driver_sql("INSERT INTO session_trial_cutoffs VALUES(?,?,?,?) ON CONFLICT DO NOTHING",
                                   (*key, version, row["event_id"]))
            else:
                raise ValueError("Unrecognized test report event")

        def cutoff(key):
            value = db.exec_driver_sql("""
                SELECT r.submitted FROM session_trial_cutoffs c JOIN session_trial_reports r
                USING(project,activity,version) WHERE c.project=? AND c.activity=?
            """, key).scalar()
            return date.fromisoformat(value) if value else None

        def claims(name):
            for number, row in enumerate(load(name), 2):
                key = row["project_code"], row["activity_code"]
                identifier = db.exec_driver_sql(
                    "INSERT INTO session_trial_claims(source,row_number,project,activity) VALUES(?,?,?,?)",
                    (name, number, *key),
                ).lastrowid
                yield key, Claim(identifier, row["staff_id"] if row["staff_id"] in staff else None,
                                 row["role"], int(row["session_number"][1:]) if row["session_number"] else None,
                                 date.fromisoformat(row["work_date"]) if row["work_date"] else None,
                                 date.fromisoformat(row["timesheet_submitted_date"])), row

        def evaluate(key, rows):
            plan = plans[key]
            return coverage(rows, start=date.fromisoformat(plan["approved_start_date"]),
                            end=date.fromisoformat(plan["approved_end_date"]), cutoff=cutoff(key))

        valid = defaultdict(list)
        for key, claim, row in claims("timesheets_valid"):
            assert row["report_id"] == reports[key]
            valid[key].append(claim)
        for key, rows in valid.items():
            result = evaluate(key, rows)
            assert result.complete
            validated = cutoff(key) is not None
            activity_states[key[1]] = "VALIDATED" if validated else "COMPLETE_REPORT_PENDING"
            for number in range(1, 7):
                pair = [claim for claim in result.accepted if claim.session == number]
                db.exec_driver_sql("INSERT INTO session_trial_occurrences VALUES(?,?,?,?)",
                                   (*key, number, pair[0].work_date.isoformat()))
                for claim in pair:
                    assignment = db.exec_driver_sql("""
                        INSERT INTO session_trial_assignments(project,activity,number,role,staff,claim_id)
                        VALUES(?,?,?,?,?,?)
                    """, (*key, number, claim.role, claim.staff_id, claim.source_row_id)).lastrowid
                    if validated:
                        db.exec_driver_sql("INSERT INTO session_trial_credits VALUES(?,?,?,?,?,?)",
                                           (f"A-{assignment:08}", claim.staff_id, plans[key]["policy_id"],
                                            "fixture-v1", key[0], assignment))
        assert activity_states == {row["activity_code"]: row["expected_state"]
                                   for row in load("verified_fixture_expectations")}
        assert cutoff(plan_ids["TEST-B-001"]) == date(2026, 7, 12)
        for key, claim, row in claims("timesheets_invalid"):
            baseline = valid.get(key, [])
            if key not in plans:
                codes = {"UNAPPROVED_ACTIVITY"}
            else:
                codes = {issue.code for issue in evaluate(key, [*baseline, claim]).issues}
                if any(item.session == claim.session and item.role != claim.role
                       and item.staff_id == claim.staff_id and item.work_date == claim.work_date
                       for item in baseline) and "ROLE_ASSIGNMENT_CONFLICT" in codes:
                    codes.add("SAME_STAFF_BOTH_ROLES")
            invalid[row["submission_id"]] = sorted(codes)
        expected_invalid = read(directory, "timesheets_invalid")[1]
        mismatches = [
            {"case": row["submission_id"], "expected": row["expected_issue"],
             "observed": invalid[row["submission_id"]]}
            for row in expected_invalid if row["expected_issue"] not in invalid[row["submission_id"]]
        ]

        for row in load("pooling_credits_synthetic"):
            assert row["test_eligibility"] == "ELIGIBLE" and row["staff_id"].startswith("TEST-")
            db.exec_driver_sql("INSERT INTO session_trial_credits VALUES(?,?,?,?,?,NULL)",
                               (row["credit_id"], row["staff_id"], row["policy_id"], "fixture-v1", row["project_code"]))
        expected_pool = load("pooling_expected")

    grouped = pool_credits(engine)
    assert pool_credits(engine) == 0
    with engine.connect() as db:
        for row in expected_pool:
            identifier = row["staff_id"]
            groups = db.exec_driver_sql("SELECT id, amount FROM session_trial_groups WHERE staff=?", (identifier,)).all()
            assert len(groups) == int(row["groups"])
            assert sum(Decimal(group.amount) for group in groups) == Decimal(row["amount_usd"])
            for policy_count in row["remainder_by_policy"].split("|"):
                policy, count = policy_count.split(":")
                actual = db.exec_driver_sql("""
                    SELECT count(*) FROM session_trial_credits c LEFT JOIN session_trial_group_credits g
                    ON c.id=g.credit_id WHERE c.staff=? AND c.policy=? AND g.credit_id IS NULL
                """, (identifier, policy)).scalar_one()
                assert actual == int(count)
            for group in groups:
                origins = db.exec_driver_sql("""
                    SELECT DISTINCT c.project FROM session_trial_credits c
                    JOIN session_trial_group_credits g ON g.credit_id=c.id WHERE g.group_id=?
                """, (group.id,)).fetchall()
                assert len(origins) > 1 and row["export_state"] == "ALLOCATION_REVIEW_REQUIRED"
                assert export_blockers(engine, group.id) == ("ALLOCATION_REVIEW_REQUIRED", "BATCH_APPROVAL_REQUIRED")
        assert db.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    return {"activities": activity_states, "invalid_cases": len(invalid), "staged_rows_blocked": len(staged),
            "fixture_mismatches": mismatches, "groups_created": grouped, "retry_groups_created": 0, "export": "disabled for synthetic trial"}


if __name__ == "__main__":
    with TemporaryDirectory(prefix="timmy-session-fixtures-") as temporary:
        print(json.dumps(trial(Path(sys.argv[1]), f"sqlite:///{temporary}/trial.db"), indent=2))
