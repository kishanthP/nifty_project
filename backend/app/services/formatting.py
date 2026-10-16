from decimal import ROUND_HALF_UP, Decimal

_PAISA = Decimal("0.01")


def to_price(value: float | Decimal | str) -> Decimal:
    """Convert to a 2-decimal Decimal (rupees and paise) without float rounding surprises."""
    return Decimal(str(value)).quantize(_PAISA, rounding=ROUND_HALF_UP)


def format_inr(value: float | Decimal) -> str:
    """Indian digit grouping: 1234567.5 -> '12,34,567.50'."""
    amount = to_price(value)
    sign = "-" if amount < 0 else ""
    whole, fraction = f"{abs(amount):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        pairs = []
        while len(head) > 2:
            pairs.insert(0, head[-2:])
            head = head[:-2]
        if head:
            pairs.insert(0, head)
        whole = ",".join([*pairs, tail])
    return f"{sign}{whole}.{fraction}"
