"""Run the workbook in a newly created, separate Timmy database."""
import argparse
import asyncio
import json
from decimal import Decimal
from getpass import getpass
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp
from time import time

from alembic import command
from alembic.config import Config
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from timmy.ai import OllamaAdapter, build_ollama_client
from timmy.audit import audit
from timmy.auth import password_hasher
from timmy.config import Settings
from timmy.database import make_engine
from timmy.demo_workbook import HeaderInterpretation, calculate, map_policy, read_workbook, reconcile, unique
from timmy.models import Role, User, WorkflowRun, activities, imports, payment_policies, project_memberships, projects, timesheets
from timmy.payment_configuration import save_draft


def evaluate(fixture, results, obligations, reconciled, exceptions):
    checks = []

    def check(case, expected, actual):
        checks.append(dict(case=case, expected=expected, actual=actual, result="PASS" if expected == actual else "FAIL"))

    def money(value):
        return format(Decimal(value), ".2f")

    for row in fixture["07_Expected_Results"]:
        actual = results[row["TimesheetID"]]
        check(row["TimesheetID"],
              [row["ExpectedOutcome"], int(row["EligibleRawUnits"]), money(row["BillableQuantity"]),
               money(row["Rate"]), money(row["ExpectedAmountUSD"]), row["ObligationID"]],
              [actual["outcome"], actual["eligible"], money(actual["billable_quantity"]),
               money(actual["rate"]), money(actual["amount"]),
               next((ref for ref, item in obligations.items() if item is actual), None)])
    for row in fixture["08_Demo_Obligations"]:
        actual = obligations.get(row["ObligationID"], {})
        check("calculated " + row["ObligationID"],
              [row["TimesheetID"], row["ProjectID"], row["VolunteerID"], money(row["ApprovedAmount"]), row["Currency"]],
              [actual.get("timesheet"), actual.get("project"), actual.get("volunteer"),
               money(actual.get("amount", 0)), actual.get("currency")])
    for row in fixture["10_Expected_Recon"]:
        actual = reconciled.get(row["ObligationID"], {})
        check("simulated " + row["ObligationID"],
              [money(row[k]) for k in ("ApprovedAmount", "NetSettled", "Outstanding")] + [row["ExpectedStatus"]],
              [money(actual.get(k, 0)) for k in ("approved", "net", "balance")] + [actual.get("status")])
    balances = [Decimal(row["balance"]) for row in reconciled.values()]
    check("timesheets processed", 14, len(results))
    check("payable candidates", 8, len(obligations))
    check("blocked timesheets", 6, sum(row["outcome"] == "BLOCKED" for row in results.values()))
    check("candidate USD", "447.50", money(sum(Decimal(row["amount"]) for row in obligations.values())))
    check("simulated matched net USD", "507.50", money(sum(Decimal(row["net"]) for row in reconciled.values())))
    check("simulated positive outstanding USD", "30.00", money(sum(max(Decimal(0), x) for x in balances)))
    check("simulated overpayment USD", "90.00", money(sum(max(Decimal(0), -x) for x in balances)))
    check("unmatched confirmations", 1, sum(row["issue"] == "UNMATCHED" for row in exceptions))
    return checks


async def interpret(config, columns):
    async with build_ollama_client(config) as http:
        return await OllamaAdapter(config, http).structured([
            {"role": "system", "content": "Interpret column headers only. Never infer authority, rules, quantities, or payments."},
            {"role": "user", "content": json.dumps(columns)},
        ], HeaderInterpretation)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--interactive", action="store_true", help="Set a demo login password and optionally authorize demo obligations")
    args = parser.parse_args()
    raw = args.workbook.read_bytes()
    fixture = read_workbook(raw)
    root = Path(mkdtemp(prefix="timmy-payment-demo-"))
    digest = sha256(raw).hexdigest()
    (root / "source.xlsx").write_bytes(raw)
    config = Settings(database_url=f"sqlite:///{root / 'demo.db'}", demo_mode=True, weekly_enabled=False,
                      document_root=root / "documents", ollama_model=args.model)
    import os
    os.environ["TIMMY_DATABASE_URL"] = config.database_url
    command.upgrade(Config("backend/alembic.ini"), "head")

    source = fixture["04_Timesheets"]
    unique(source, "TimesheetID")
    interpretation = asyncio.run(interpret(config, [k for k in source[0] if k != "source_row"]))
    project_rows = unique(fixture["01_Project_Policies"], "ProjectID")
    policies = {code: map_policy(row) for code, row in project_rows.items()}
    plans = unique(fixture["02_Approved_Activities"], "ActivityCode")
    volunteers = unique(fixture["03_Volunteers"], "VolunteerID")
    results = calculate(policies, plans, volunteers, source,
                        unique(fixture["05_Report_Evidence"], "ActivityCode"),
                        unique(fixture["06_Human_Reviews"], "TimesheetID"))
    obligations = {f"OBL-{i:03}": row for i, row in enumerate(
        (row for row in results if row["outcome"] != "BLOCKED"), 1)}
    print("DEMO calculation candidates (synthetic evidence):")
    for reference, row in obligations.items():
        print(reference, row["timesheet"], row["volunteer"], row["currency"], row["amount"])
    approved = False
    if args.interactive:
        password = getpass("Create password for demo-admin (12+ characters): ")
        if len(password) < 12:
            raise ValueError("Password must have at least 12 characters")
        approved = input("Type AUTHORIZE DEMO to authorize the exact listed simulated obligations: ") == "AUTHORIZE DEMO"
    else:
        from secrets import token_urlsafe
        password = token_urlsafe(32)

    # A separate test projection compares expected reconciliations. Only explicit
    # interactive authorization permits that projection to represent approved demo state.
    returns = fixture["09_Demo_Payment_Return"]
    simulated, exceptions = reconcile(obligations, returns)
    checks = evaluate(fixture, {row["timesheet"]: row for row in results}, obligations, simulated, exceptions)
    engine = make_engine(config.database_url)
    with Session(engine) as db, db.begin():
        role = Role(name="admin")
        db.add(role)
        db.flush()
        actor = User(username="demo-admin", password_hash=password_hasher.hash(password), role_id=role.id)
        db.add(actor)
        db.flush()
        for code, policy in policies.items():
            pid = db.execute(insert(projects).values(name=project_rows[code]["ProjectName"], project_code=code,
                                                    status="active")).inserted_primary_key[0]
            db.execute(insert(project_memberships).values(project_id=pid, user_id=actor.id))
            policy_id = save_draft(db, pid, actor.id, policy)
            db.execute(update(payment_policies).where(payment_policies.c.id == policy_id).values(
                status="active", activated_at=int(time()), activated_by=actor.id))
            audit(db, "demo_fixture_policy_activated", actor.id, resource_type="payment_policy", resource_id=str(policy_id))
            for plan in plans.values():
                if plan["ProjectID"] == code and plan["PlanningStatus"] == "APPROVED":
                    db.execute(insert(activities).values(project_id=pid, name=f'{plan["ActivityCode"]} · {plan["ActivityName"]}'))
            import_id = db.execute(insert(imports).values(project_id=pid, uploaded_by=actor.id,
                source_name="DEMO · " + args.workbook.name + " · 04_Timesheets")).inserted_primary_key[0]
            for row in source:
                if row["ProjectID"] == code:
                    db.execute(insert(timesheets).values(import_id=import_id,
                        source_row=row["source_row"], source_values=row))
            scoped = {key: value for key, value in obligations.items() if value["project"] == code}
            snapshot = dict(environment="DEMO", source_sha256=digest, policy_id=policy_id,
                            policy_origin=project_rows[code], qwen_mapping=interpretation.model_dump(),
                            qwen_model=args.model, import_id=import_id,
                            results=[row for row in results if row["project"] == code],
                            approvals={key: {"actor_id": actor.id, "at": int(time())} for key in scoped} if approved else {},
                            obligations=scoped, reconciliation={key: simulated[key] for key in scoped} if approved else {},
                            confirmations=[row for row in returns
                                           if approved and row["ApprovedObligationReference"] in scoped])
            db.add(WorkflowRun(actor_id=actor.id, project_id=pid, request_key=f"demo-workbook:{code}",
                               fingerprint=digest, workflow_id="demo_workbook", knowledge_version="1",
                               created_at=int(time()), status="reconciled_demo" if approved else "pending_human_approval",
                               snapshot=snapshot))
            if approved:
                audit(db, "demo_obligations_authorized", actor.id, resource_type="project", resource_id=str(pid))
                audit(db, "demo_confirmations_reconciled", actor.id, resource_type="project", resource_id=str(pid),
                      trigger="demo_workbook", outcome="simulated")
    report = root / "evaluation.json"
    report.write_text(json.dumps(dict(environment="DEMO", approved=approved, confirmation_exceptions=exceptions,
                                      reconciliation_is_test_projection=not approved, checks=checks), indent=2))
    print(f"Database: {root / 'demo.db'}\nEvaluation: {report}")
    print(f"{sum(row['result'] == 'PASS' for row in checks)}/{len(checks)} checks passed")
    if any(row["result"] == "FAIL" for row in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
