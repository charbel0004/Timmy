"""Read-only checks of spreadsheet claims. Uploaded reference rows are provisional."""
import re
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date

from .session_rules import Claim, coverage

TIMESHEET = {"project_code", "activity_code", "staff_id", "role", "session_number",
             "work_date", "timesheet_submitted_date"}
PLANNING = {"project_code", "activity_code", "approved_start_date", "approved_end_date"}
DIRECTORY = {"staff_id", "status"}
ROLES = {
    "trainer": "TRAINER", "facilitator": "TRAINER", "ميسّر": "TRAINER", "مدرّب": "TRAINER",
    "logistic": "LOGISTIC", "logistics": "LOGISTIC", "لوجستيات": "LOGISTIC",
}


def parse_date(value):
    try:
        return date.fromisoformat(value) if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) else None
    except ValueError:
        return None


def escape(value):
    return re.sub(r"([^\w\s])", r"\\\1", " ".join(value.split()))


def preview(documents):
    plans = defaultdict(set)
    directory = defaultdict(set)
    claims = defaultdict(list)
    issues = defaultdict(Counter)
    evidence = defaultdict(set)
    seen = set()
    matched = False
    unparsed = 0
    for file, record in documents:
        fingerprint = (file.project_id, file.sha256)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        for sheet in record.sheets:
            rows = sheet["rows"]
            if not rows:
                continue
            headers = [str(value or "").strip().casefold() for value in rows[0]["values"]]
            names = set(headers)
            if len(headers) != len(names):
                unparsed += 1
                continue
            if TIMESHEET <= names:
                kind = "claims"
                matched = True
            elif PLANNING <= names:
                kind = "planning"
            elif DIRECTORY <= names:
                kind = "directory"
            else:
                unparsed += 1
                continue
            for source in rows[1:]:
                row = dict(zip(headers, (str(value or "").strip() for value in source["values"])))
                key = (file.project_id, row.get("project_code", ""), row.get("activity_code", ""))
                if kind == "planning":
                    plans[key].add((row.get("approved_start_date", ""), row.get("approved_end_date", "")))
                elif kind == "directory":
                    directory[file.project_id, row.get("staff_id", "")].add(row.get("status", "").casefold())
                else:
                    evidence[key].add(file.original_filename)
                    if not all(key):
                        issues[key]["MISSING_PROJECT_OR_ACTIVITY_CODE"] += 1
                    claim_date = parse_date(row.get("work_date", ""))
                    submitted = parse_date(row.get("timesheet_submitted_date", ""))
                    if not submitted:
                        issues[key]["MISSING_OR_INVALID_SUBMISSION_DATE"] += 1
                    session = re.fullmatch(r"S?([0-9]{1,3})", row.get("session_number", "").upper())
                    claims[key].append((row.get("staff_id", ""), Claim(
                        len(claims[key]) + 1, None, ROLES.get(row.get("role", "").casefold()),
                        int(session[1]) if session else None, claim_date, submitted or date.min,
                    )))

    if not matched:
        return None
    lines = ["### Session-policy preview",
             "This read-only check uses uploaded claims and reference files. Payment eligibility remains blocked until planning, staff identities, and external report validation are independently verified."]
    if unparsed:
        lines.append(f"{unparsed} sheet(s) were not used. They were reference-only or did not match a supported header layout.")
    if not claims:
        lines.append("The recognized timesheet has no source claims.")
    for key in sorted(claims):
        _, project, activity = key
        if len(lines) > 65:
            lines.append("Additional activities omitted. Ask for a smaller set of uploads.")
            break
        codes = issues[key]
        candidates = plans[key]
        start, end = None, None
        if len(candidates) == 1:
            start, end = map(parse_date, next(iter(candidates)))
        window_ok = start is not None and end is not None and start <= end
        if not window_ok:
            codes["PLANNING_WINDOW_MISSING_OR_CONFLICTING"] += 1
        normalized = []
        for staff, claim in claims[key]:
            if not staff or directory[key[0], staff] != {"active"}:
                codes["STAFF_NOT_MATCHED_TO_ACTIVE_DIRECTORY"] += 1
            normalized.append(replace(claim, staff_id=staff or None))
        result = coverage(normalized, start=start if window_ok else date.min, end=end if window_ok else date.max)
        codes.update(issue.code for issue in result.issues)
        status = "Structure passes preview" if result.complete and not codes else "Needs review"
        lines.extend([
            f"\n**{escape(project or 'Unknown project')} / {escape(activity or 'Unknown activity')}**",
            f"- Status: {status} · {len(result.accepted) // 2}/6 session pairs · {len(result.accepted)}/12 role slots.",
            f"- Preview issues: {', '.join(f'{code} ({count})' for code, count in sorted(codes.items())) or 'None detected'}.",
            "- Payment eligible: No. Approval and export were not performed.",
            f"- Timesheet evidence: {', '.join(escape(name) for name in sorted(evidence[key]))}.",
        ])
    return "\n".join(lines)
