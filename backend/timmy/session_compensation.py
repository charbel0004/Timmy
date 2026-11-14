"""Exact session grouping from the approved session policy contract v1.0."""
from decimal import Decimal

SESSION_GROUP_SIZE = 3
SESSION_GROUP_RATE = Decimal("25.00")
SESSION_CURRENCY = "USD"


def session_compensation(eligible_credits: int) -> tuple[Decimal, int]:
    """Return exact compensation and unconsumed credits after eligibility is established."""
    if type(eligible_credits) is not int or eligible_credits < 0:
        raise ValueError("Eligible credits must be a nonnegative integer")
    groups, remaining = divmod(eligible_credits, SESSION_GROUP_SIZE)
    return groups * SESSION_GROUP_RATE, remaining
