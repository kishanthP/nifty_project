from decimal import Decimal

from app.services.alerts import infer_condition, is_condition_met
from app.services.formatting import format_inr, to_price


def test_indian_grouping() -> None:
    assert format_inr(22560) == "22,560.00"
    assert format_inr(1234567.5) == "12,34,567.50"
    assert format_inr(999) == "999.00"


def test_to_price_rounds_half_up() -> None:
    assert to_price(22560.005) == Decimal("22560.01")
    assert to_price("22540") == Decimal("22540.00")


def test_condition_rules_match_user_example() -> None:
    current = Decimal("22550")
    assert infer_condition(Decimal("22560"), current) == "above"
    assert infer_condition(Decimal("22540"), current) == "below"
    assert is_condition_met("above", Decimal("22560"), Decimal("22560"))
    assert not is_condition_met("above", Decimal("22560"), Decimal("22559.95"))
    assert is_condition_met("below", Decimal("22540"), Decimal("22540"))
