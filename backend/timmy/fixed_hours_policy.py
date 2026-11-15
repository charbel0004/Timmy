"""Fixed, deterministic hourly arithmetic for review-only payment candidates.

This pure module does NOT confer planning/report/identity/payment authority, create
entitlements, or approve/export/settle money. Only verified, eligible source
intervals should ever be passed by a future backend integration. All money USD.

Pending NK decisions remain blockers: exactly-15-minute rounding ties,
overnight month-boundary attribution and cross-activity overlap cost attribution.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable
from zoneinfo import ZoneInfo

RATE_USD = Decimal("5.00")
MAX_MONTHLY_PAYABLE_HOURS = 120
MAX_ROLLING_24H_MINUTES = 16 * 60
BEIRUT = ZoneInfo("Asia/Beirut")


class HoursPolicyError(ValueError):
    """A source or rule is invalid; original evidence must be preserved."""


@dataclass(frozen=True)
class HourlyShift:
    staff_id: str
    project_code: str
    activity_code: str
    role: str
    start: datetime
    end: datetime
    source_id: str

    def __post_init__(self):
        if not all((self.staff_id, self.project_code, self.activity_code, self.role, self.source_id)):
            raise HoursPolicyError("MISSING_REQUIRED_SHIFT_FIELD")
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise HoursPolicyError("EXPLICIT_TIMEZONE_REQUIRED")
        if any((self.start.second, self.start.microsecond, self.end.second, self.end.microsecond)):
            raise HoursPolicyError("UNSUPPORTED_SUBMINUTE_TIME")
        if self.end <= self.start:
            raise HoursPolicyError("INVALID_SHIFT_INTERVAL")


@dataclass(frozen=True)
class HourlyMonthCandidate:
    staff_id: str
    project_code: str
    year: int
    month: int
    source_ids: tuple[str, ...]
    actual_unique_minutes: int
    rounded_minutes: int
    payable_hours: int | None
    amount_usd: Decimal | None
    blockers: tuple[str, ...]  # Nonempty => NOT payable / no financial release.


def _minutes(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 60)


def _utc_interval(shift: HourlyShift) -> tuple[datetime, datetime]:
    a, b = shift.start.astimezone(timezone.utc), shift.end.astimezone(timezone.utc)
    if b <= a:
        raise HoursPolicyError("INVALID_SHIFT_INTERVAL")
    return a, b


def _merged(intervals: Iterable[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    result: list[tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if result and start < result[-1][1]:  # Adjacent shifts remain distinct for rounding.
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def rounded_half_hour_minutes(actual_minutes: int) -> int:
    """Nearest half hour. Exactly 15-minute ties are NOT approved: block."""
    if type(actual_minutes) is not int or actual_minutes < 0:
        raise HoursPolicyError("INVALID_DURATION")
    units, remainder = divmod(actual_minutes, 30)
    if remainder == 15:
        raise HoursPolicyError("HALF_HOUR_TIE_RULE_UNCONFIRMED")
    return (units + (1 if remainder > 15 else 0)) * 30


def _rolling_24h_exceeded(intervals: list[tuple[datetime, datetime]]) -> bool:
    """Exact unique actual time in every rolling 24h ending at a shift boundary."""
    merged = _merged(intervals)
    for _, boundary in merged:
        start = boundary - timedelta(hours=24)
        worked = sum(max(0, _minutes(max(a, start), min(b, boundary)))
                     for a, b in merged if a < boundary and b > start)
        if worked > MAX_ROLLING_24H_MINUTES:
            return True
    return False


def monthly_candidates(shifts: Iterable[HourlyShift]) -> list[HourlyMonthCandidate]:
    """Compute non-authoritative previews; never mark these eligible for export.

    Same-role overlaps in the same project are unioned before duration rounding.
    Different-role overlaps are held for review. Cross-project overlaps are
    held for cost attribution even when the roles match. Rolling limits span
    all submitted hourly-policy projects for the same verified staff ID.
    """
    provided = list(shifts)
    seen: dict[str, HourlyShift] = {}
    for shift in provided:
        if shift.source_id in seen and shift != seen[shift.source_id]:
            raise HoursPolicyError("SOURCE_ID_COLLISION")
        seen[shift.source_id] = shift
    all_shifts = list(seen.values())
    by_staff: dict[str, list[HourlyShift]] = {}
    for shift in all_shifts:
        by_staff.setdefault(shift.staff_id, []).append(shift)
    results: list[HourlyMonthCandidate] = []

    for staff, worker_shifts in sorted(by_staff.items()):
        intervals = [(s, *_utc_interval(s)) for s in worker_shifts]
        rolling_exceeded = _rolling_24h_exceeded([(a, b) for _, a, b in intervals])
        buckets: dict[tuple[str, int, int], list[HourlyShift]] = {}
        held: dict[tuple[str, int, int], set[str]] = {}
        for shift, start, end in intervals:
            local_start, local_end = start.astimezone(BEIRUT), end.astimezone(BEIRUT)
            key = (shift.project_code, local_start.year, local_start.month)
            buckets.setdefault(key, []).append(shift)
            if (local_start.year, local_start.month) != (local_end.year, local_end.month):
                held.setdefault(key, set()).add("CROSS_MONTH_SHIFT_ATTRIBUTION_REQUIRED")
            if rolling_exceeded:
                held.setdefault(key, set()).add("ROLLING_24H_OVER_16_HOURS")

        # Detect overlaps across the worker's complete set, not within one file
        # or project. Shared time is never silently attributed to two roles.
        for i, (first, start_a, end_a) in enumerate(intervals):
            for second, start_b, end_b in intervals[i + 1:]:
                if start_a >= end_b or start_b >= end_a:
                    continue
                if first.role != second.role:
                    issue = "DIFFERENT_ROLE_OVERLAP_REVIEW_REQUIRED"
                elif first.project_code != second.project_code:
                    issue = "CROSS_PROJECT_OVERLAP_ALLOCATION_REQUIRED"
                elif first.activity_code != second.activity_code:
                    issue = "CROSS_ACTIVITY_OVERLAP_ALLOCATION_REQUIRED"
                else:
                    continue  # Same staff/project/role/activity: union below.
                for shift in (first, second):
                    local = shift.start.astimezone(BEIRUT)
                    held.setdefault((shift.project_code, local.year, local.month), set()).add(issue)

        for (project, year, month), grouped in sorted(buckets.items()):
            blockers = held.setdefault((project, year, month), set())
            # Always preserve exact source references; avoid inference of missing
            # reporting/identity/planning authority, which is checked upstream.
            raw_union = _merged([_utc_interval(s) for s in grouped])
            actual = sum(_minutes(a, b) for a, b in raw_union)
            # Union only same-role overlapping claims. Distinct roles' overlapping
            # time stays blocked, so preview cannot authorize duplicate wages.
            by_role: dict[str, list[tuple[datetime, datetime]]] = {}
            for shift in grouped:
                by_role.setdefault(shift.role, []).append(_utc_interval(shift))
            total_rounded = 0
            for role_intervals in by_role.values():
                for a, b in _merged(role_intervals):
                    try:
                        total_rounded += rounded_half_hour_minutes(_minutes(a, b))
                    except HoursPolicyError as error:
                        blockers.add(str(error))
            whole_hours = min(total_rounded // 60, MAX_MONTHLY_PAYABLE_HOURS)
            results.append(HourlyMonthCandidate(
                staff_id=staff, project_code=project, year=year, month=month,
                source_ids=tuple(sorted(s.source_id for s in grouped)),
                actual_unique_minutes=actual, rounded_minutes=total_rounded,
                payable_hours=None if blockers else whole_hours,
                amount_usd=None if blockers else RATE_USD * whole_hours,
                blockers=tuple(sorted(blockers))))
    return results
