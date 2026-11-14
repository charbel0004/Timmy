"""Deterministic checks for normalized, server-resolved session claims."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from itertools import groupby


@dataclass(frozen=True)
class Claim:
    source_row_id: int
    staff_id: str | None
    role: str | None
    session: int | None
    work_date: date | None
    submitted: date


@dataclass(frozen=True)
class Issue:
    code: str
    source_rows: tuple[int, ...]


@dataclass(frozen=True)
class Coverage:
    accepted: tuple[Claim, ...]
    issues: tuple[Issue, ...]

    @property
    def complete(self) -> bool:
        return len(self.accepted) == 12 and not self.issues


def coverage(claims: list[Claim], *, start: date, end: date, cutoff: date | None = None) -> Coverage:
    """Evaluate one planning-approved project/activity. Conflicts require review."""
    issues = []
    slots: dict[int, list[Claim]] = defaultdict(list)
    for claim in claims:
        work = claim.work_date
        code = None
        if not claim.staff_id:
            code = "MISSING_STAFF_ID"
        elif claim.role not in {"TRAINER", "LOGISTIC"}:
            code = "ROLE_UNKNOWN"
        elif claim.session is None:
            code = "MISSING_SESSION_NUMBER"
        elif claim.session not in range(1, 7):
            code = "SESSION_COUNT_EXCEEDS_ACTIVITY"
        elif work is None:
            code = "MISSING_SESSION_DATE"
        elif not start <= work <= end:
            code = "PLANNED_DATE_OUT_OF_RANGE"
        elif claim.submitted < work:
            code = "SUBMISSION_PRECEDES_WORK"
        elif cutoff is not None and work > cutoff:
            code = "AFTER_VALIDATED_REPORT_CUTOFF"
        if code:
            issues.append(Issue(code, (claim.source_row_id,)))
        else:
            slots[claim.session].append(claim)

    accepted = []
    dates = []
    for number in range(1, 7):
        candidates = slots[number]
        sources = tuple(claim.source_row_id for claim in candidates)
        counts = Counter(claim.role for claim in candidates)
        identities = Counter((claim.staff_id, claim.role, claim.work_date) for claim in candidates)
        if any(count > 1 for count in identities.values()):
            issues.append(Issue("DUPLICATE_CLAIM", sources))
        elif any(count > 1 for count in counts.values()):
            issues.append(Issue("ROLE_ASSIGNMENT_CONFLICT", sources))
        elif len(candidates) != 2:
            issues.append(Issue("INCOMPLETE_OCCURRENCE", sources))
        elif candidates[0].staff_id == candidates[1].staff_id:
            issues.append(Issue("SAME_STAFF_BOTH_ROLES", sources))
        elif candidates[0].work_date != candidates[1].work_date:
            issues.append(Issue("SESSION_DATE_MISMATCH", sources))
        else:
            accepted.extend(candidates)
            dates.append(candidates[0].work_date)
    if len(dates) == 6:
        runs = tuple(len(list(group)) for _, group in groupby(dates))
        if dates != sorted(dates) or runs not in {(3, 3), (2, 2, 2)}:
            issues.append(Issue("INVALID_DATE_PATTERN", tuple(claim.source_row_id for claim in accepted)))
    return Coverage(tuple(accepted), tuple(issues))
