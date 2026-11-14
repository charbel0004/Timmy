"""Explicit adapter for the synthetic AlphaHack workbook. No live authority."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .documents import parse
from .payment_configuration import PolicyConfiguration, example_calculation

HEADERS = {
    "01_Project_Policies": "ProjectID ProjectName PolicyType Rate Currency EffectiveFrom EffectiveTo DurationRounding OvernightRule DailyCap MoneyRounding PolicyEvidence",
    "02_Approved_Activities": "ActivityCode ProjectID ActivityName ActivityDate PlanningStatus PlanningEvidence",
    "03_Volunteers": "VolunteerID|DisplayName (synthetic)|Status",
    "04_Timesheets": "TimesheetID ProjectID ActivityCode VolunteerID WorkDate StartTime EndTime Minutes Sessions SubmissionStatus Scenario",
    "05_Report_Evidence": "ActivityCode ReportStatus ExternalEvidenceRef Notes",
    "06_Human_Reviews": "TimesheetID PlanningDecision StaffDecision PlanningEvidence StaffEvidence",
    "07_Expected_Results": "TimesheetID ExpectedOutcome EligibleRawUnits BillableQuantity Rate ExpectedAmountUSD ObligationID Reason",
    "08_Demo_Obligations": "ObligationID TimesheetID ProjectID VolunteerID ApprovedAmount Currency HumanApproval ApprovalEvidence Environment",
    "09_Demo_Payment_Return": "ExternalConfirmationID ApprovedObligationReference Amount Currency PaymentStatus PaymentDate ExternalSource ReversalReference",
    "10_Expected_Recon": "ObligationID ApprovedAmount NetSettled Outstanding ExpectedStatus Evidence",
    "00_Read_Me": "Item Value",
    "11_Test_Instructions": "Stage Instructions",
}


def read_workbook(raw):
    sheets, _ = parse(raw, ".xlsx")
    if {s["name"] for s in sheets} != HEADERS.keys() or len(sheets) != len(HEADERS):
        raise ValueError("Unexpected demo worksheet layout")
    result = {}
    for sheet in sheets:
        name = sheet["name"]
        header = HEADERS[name]
        expected = header.split("|") if "|" in header else header.split()
        rows = sheet["rows"]
        if not rows or rows[0]["values"] != expected:
            raise ValueError(f"Unexpected columns in {name}")
        result[name] = [dict(zip(expected, row["values"], strict=True)) | {"source_row": row["row"]}
                        for row in rows[1:]]
    return result


def unique(rows, key):
    indexed = {}
    for row in rows:
        value = row[key]
        if not value or value in indexed:
            raise ValueError(f"Missing or duplicate {key}")
        indexed[value] = row
    return indexed


class HeaderInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: Literal["StartTime"]
    end: Literal["EndTime"]
    minutes: Literal["Minutes"]
    sessions: Literal["Sessions"]


def map_policy(row):
    hours = row["PolicyType"] == "Hours"
    if row["PolicyType"] not in {"Hours", "Sessions"} or row["MoneyRounding"] != "Half-up 2 decimals":
        raise ValueError("Unsupported demo policy")
    if (row["DurationRounding"], row["OvernightRule"]) != (
            ("Exact minute", "Continuous elapsed") if hours else ("N/A", "N/A")):
        raise ValueError("Unsupported duration rule")
    cap, unit = row["DailyCap"].split()
    if unit != ("hours/day" if hours else "sessions/day"):
        raise ValueError("Unsupported daily cap unit")
    if row["PolicyEvidence"] != "DEMO - administrator confirmed":
        raise ValueError("Missing synthetic policy authority marker")
    return PolicyConfiguration(
        family="hours" if hours else "session", rate=row["Rate"], currency=row["Currency"],
        start=row["EffectiveFrom"], end=row["EffectiveTo"], daily_cap=int(cap) * (60 if hours else 1),
        eligibility="approved_evidence_only", precision=2, monetary_rounding="half_up",
        duration_rounding="exact" if hours else None, overnight="continuous" if hours else None,
    )


def calculate(policies, activities, volunteers, timesheets, reports, reviews):
    accepted = defaultdict(list)
    used_daily = defaultdict(int)
    results = []
    for row in timesheets:
        ts, project, activity, person = (row[k] for k in ("TimesheetID", "ProjectID", "ActivityCode", "VolunteerID"))
        policy = policies[project]
        day = date.fromisoformat(row["WorkDate"])
        plan = activities.get(activity, {})
        review = reviews.get(ts, {})
        report = reports.get(activity, {})
        reasons = []
        if (plan.get("ProjectID"), plan.get("ActivityDate"), plan.get("PlanningStatus")) != (
                project, row["WorkDate"], "APPROVED") or not plan.get("PlanningEvidence"):
            reasons.append("UNAPPROVED_ACTIVITY")
        if report.get("ReportStatus") != "APPROVED" or not report.get("ExternalEvidenceRef"):
            reasons.append("MISSING_REPORT")
        if volunteers.get(person, {}).get("Status") != "Active":
            reasons.append("STAFF_NOT_ACTIVE")
        for kind in ("Planning", "Staff"):
            if review.get(kind + "Decision") != "APPROVED" or not review.get(kind + "Evidence"):
                reasons.append(kind.upper() + "_APPROVAL_REQUIRED")
        if not policy.start <= day <= (policy.end or date.max) or row["SubmissionStatus"] != "SUBMITTED":
            reasons.append("SUBMISSION_OR_POLICY_DATE_INVALID")
        interval = None
        raw = int(row["Minutes"] if policy.family == "hours" else row["Sessions"])
        if policy.family == "hours":
            start = datetime.combine(day, time.fromisoformat(row["StartTime"]))
            end = datetime.combine(day, time.fromisoformat(row["EndTime"]))
            if end < start:
                end += timedelta(days=1)
            interval = (start, end)
            if end - start != timedelta(minutes=raw) or int(row["Sessions"]):
                reasons.append("INVALID_DURATION")
        elif row["StartTime"] or row["EndTime"] or int(row["Minutes"]):
            reasons.append("MIXED_QUANTITY")
        for prior_activity, prior_day, prior_interval in accepted[person]:
            if activity == prior_activity and day == prior_day and interval == prior_interval:
                reasons.append("DUPLICATE")
            elif interval and prior_interval and max(interval[0], prior_interval[0]) < min(interval[1], prior_interval[1]):
                reasons.append("OVERLAP")
        key = (project, person, day)
        quantity = max(0, min(raw, policy.daily_cap - used_daily[key]))
        if raw <= 0 or not quantity:
            reasons.append("NO_ELIGIBLE_QUANTITY")
        if reasons:
            quantity = 0
        else:
            accepted[person].append((activity, day, interval))
            used_daily[key] += quantity
        amount = example_calculation(policy, quantity)["amount"]
        results.append({"timesheet": ts, "project": project, "activity": activity, "volunteer": person,
                        "raw": raw, "eligible": quantity, "excluded": raw - quantity,
                        "billable_quantity": str(Decimal(quantity) / (60 if policy.family == "hours" else 1)),
                        "rate": str(policy.rate), "currency": policy.currency, "amount": amount,
                        "outcome": "BLOCKED" if reasons else "ELIGIBLE_CAPPED" if quantity < raw else "ELIGIBLE",
                        "reasons": sorted(set(reasons)), "planning": plan, "report": report,
                        "review": review, "source_row": row["source_row"]})
    return results


def reconcile(obligations, rows):
    net = defaultdict(Decimal)
    reversed_amount = defaultdict(Decimal)
    seen = {}
    exceptions = []
    for row in rows:
        identifier, reference = row["ExternalConfirmationID"], row["ApprovedObligationReference"]
        if identifier in seen:
            exceptions.append({"id": identifier, "issue": "DUPLICATE_CONFIRMATION"})
            continue
        seen[identifier] = None
        obligation = obligations.get(reference)
        issue = None
        amount = Decimal(row["Amount"])
        status = row["PaymentStatus"]
        if not obligation:
            issue = "UNMATCHED"
        elif row["Currency"] != obligation["currency"]:
            issue = "CURRENCY_MISMATCH"
        elif (not identifier or row["ExternalSource"] != "DEMO_IMPORT" or not amount.is_finite()
              or amount <= 0 or amount != amount.quantize(Decimal("0.01"))):
            issue = "INVALID_CONFIRMATION"
        elif status == "SETTLED" and not row["ReversalReference"]:
            net[reference] += amount
            seen[identifier] = (reference, amount, date.fromisoformat(row["PaymentDate"]))
        elif status == "REVERSED":
            original_id = row["ReversalReference"]
            original = seen.get(original_id)
            if (not original or original[0] != reference or reversed_amount[original_id] + amount > original[1]
                    or date.fromisoformat(row["PaymentDate"]) < original[2]):
                issue = "INVALID_REVERSAL"
            else:
                net[reference] -= amount
                reversed_amount[original_id] += amount
        else:
            issue = "INVALID_CONFIRMATION_STATUS"
        if issue:
            exceptions.append({"id": identifier, "issue": issue})
    results = {}
    for reference, obligation in obligations.items():
        approved = Decimal(obligation["amount"])
        balance = approved - net[reference]
        status = ("OVERPAID_EXCEPTION" if balance < 0 else "PAID" if balance == 0 else
                  "PARTIALLY_PAID" if net[reference] else "UNPAID")
        results[reference] = {"approved": str(approved), "net": str(net[reference]),
                              "balance": str(balance), "status": status}
    return results, exceptions
