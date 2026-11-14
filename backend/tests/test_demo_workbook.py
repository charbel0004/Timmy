from timmy.demo_workbook import reconcile
from timmy.demo_operations import summary


def test_demo_reconciliation_keeps_positive_and_negative_balances_separate():
    obligations = {"A": {"currency": "USD", "amount": "50"}, "B": {"currency": "USD", "amount": "50"}}

    def event(identifier, target, amount, status="SETTLED", reversal=None, currency="USD"):
        return dict(ExternalConfirmationID=identifier, ApprovedObligationReference=target, Amount=amount,
                    PaymentStatus=status, ReversalReference=reversal, Currency=currency,
                    ExternalSource="DEMO_IMPORT", PaymentDate="2026-11-14")

    results, exceptions = reconcile(obligations, [
        event("1", "A", "40"), event("2", "A", "10", "REVERSED", "1"),
        event("3", "B", "70"), event("3", "B", "70"), event("4", "C", "5"),
        event("5", "B", "5", currency="LBP"), event("6", "A", "99", "REVERSED", "1"),
    ])
    assert results["A"]["status"] == "PARTIALLY_PAID"
    assert results["B"]["status"] == "OVERPAID_EXCEPTION"
    assert {row["issue"] for row in exceptions} == {
        "DUPLICATE_CONFIRMATION", "UNMATCHED", "CURRENCY_MISMATCH", "INVALID_REVERSAL",
    }
    assert summary([{"obligations": obligations, "reconciliation": results}])["USD"] == {
        "calculated": "100", "net": "100", "outstanding": "20", "overpaid": "20",
    }
