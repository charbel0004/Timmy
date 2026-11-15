"""Pure synthetic tests: no project, report, staff or payment authority is implied."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from timmy.fixed_hours_policy import (
    HourlyShift, HoursPolicyError, monthly_candidates,
    rounded_half_hour_minutes,
)


def shift(identifier, day, minutes, *, start_hour=9, staff="STAFF-1", project="FOS",
          role="LOGISTIC", activity="26-FOS-001"):
    start = datetime(2026, 9, day, start_hour, tzinfo=timezone.utc)
    return HourlyShift(staff, project, activity, role, start, start + timedelta(minutes=minutes), identifier)


@pytest.mark.parametrize(("actual","rounded"), [(250,240), (260,270), (270,270),
                                                    (280,270), (290,300), (320,330)])
def test_shift_rounding(actual, rounded):
    assert rounded_half_hour_minutes(actual) == rounded


def test_exact_tie_is_blocked_until_authorized():
    with pytest.raises(HoursPolicyError, match="HALF_HOUR_TIE"):
        rounded_half_hour_minutes(255)


def test_monthly_half_hour_expires_and_does_not_round_up():
    result = monthly_candidates([shift("a",8,260), shift("b",9,250)])[0]
    assert result.rounded_minutes == 510
    assert result.payable_hours == 8
    assert result.amount_usd == Decimal("40.00")
    assert not result.blockers


def test_monthly_cap_applies_per_staff_per_project_not_all_staff():
    shifts = [shift(f"day-{i}",i,480) for i in range(1,17)]
    shifts.append(shift("another",20,480,staff="STAFF-2"))
    outcomes = monthly_candidates(shifts)
    assert [(x.staff_id,x.payable_hours,x.amount_usd) for x in outcomes] == [
        ("STAFF-1",120,Decimal("600.00")),
        ("STAFF-2",8,Decimal("40.00")),
    ]


def test_overnight_normal_rate():
    result = monthly_candidates([shift("overnight",10,480,start_hour=20)])[0]
    assert result.payable_hours == 8 and result.amount_usd == Decimal("40.00")


def test_identical_role_overlap_is_counted_once():
    first = shift("a",10,240,start_hour=9)
    second = shift("b",10,240,start_hour=11)
    result = monthly_candidates([first,second])[0]
    assert result.actual_unique_minutes == 360
    assert result.rounded_minutes == 360
    assert result.amount_usd == Decimal("30.00")


def test_different_role_overlap_is_blocked():
    result = monthly_candidates([
        shift("a",10,240),shift("b",10,240,start_hour=10,role="TRAINER"),
    ])[0]
    assert "DIFFERENT_ROLE_OVERLAP_REVIEW_REQUIRED" in result.blockers
    assert result.amount_usd is None


def test_source_replay_cannot_mint_additional_payment():
    example=shift("same",9,240)
    result=monthly_candidates([example,example])[0]
    assert result.amount_usd == Decimal("20.00")
    assert result.source_ids == ("same",)


def test_rolling_24h_uses_actual_clock_minutes_before_rounding():
    result=monthly_candidates([shift("long",10,970)])[0]
    assert "ROLLING_24H_OVER_16_HOURS" in result.blockers
    assert result.amount_usd is None


def test_cross_month_shift_needs_authorized_attribution_rule():
    midnight=datetime(2026,9,30,20,tzinfo=timezone.utc)
    example=HourlyShift("S1","FOS","26-FOS-001","LOGISTIC",midnight,
                        midnight+timedelta(hours=8),"cross-month")
    assert "CROSS_MONTH_SHIFT_ATTRIBUTION_REQUIRED" in monthly_candidates([example])[0].blockers


def test_cross_project_overlapping_hours_are_not_silently_allocated():
    outcomes=monthly_candidates([shift("p1",10,240),shift("p2",10,240,project="OTH")])
    assert len(outcomes)==2
    assert all("CROSS_PROJECT_OVERLAP_ALLOCATION_REQUIRED" in o.blockers for o in outcomes)
    assert all(o.amount_usd is None for o in outcomes)
