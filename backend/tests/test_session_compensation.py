from decimal import Decimal

import pytest

from timmy.session_compensation import session_compensation


@pytest.mark.parametrize(("credits", "amount", "remainder"), [
    (0, "0.00", 0), (2, "0.00", 2), (3, "25.00", 0), (8, "50.00", 2),
])
def test_exact_session_group_amount(credits, amount, remainder):
    assert session_compensation(credits) == (Decimal(amount), remainder)


@pytest.mark.parametrize("credits", [-1, True, Decimal("2.5")])
def test_invalid_credit_count_is_rejected(credits):
    with pytest.raises(ValueError):
        session_compensation(credits)
