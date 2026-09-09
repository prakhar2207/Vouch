from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal('0.01')
FOUR_DECIMALS = Decimal('0.0001')

def to_decimal(val, default='0.00') -> Decimal:
    """
    Safely converts any value to Decimal without passing through float.
    """
    if val is None or val == '':
        return Decimal(str(default))
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal(str(default))

def quantize_money(val) -> Decimal:
    """
    Quantizes a currency value to 2 decimal places with half-up rounding.
    """
    d = to_decimal(val)
    return d.quantize(CENT, rounding=ROUND_HALF_UP)

def round_off_invoice(total_amount) -> tuple[Decimal, Decimal]:
    """
    Calculates standard invoice round-off:
    - If decimal remainder < 0.50, floor to integer.
    - If decimal remainder >= 0.50, ceil to next integer.
    Returns: (rounded_total, round_off_difference)
    Where rounded_total = total_amount + round_off_difference.
    """
    total = quantize_money(total_amount)
    integer_part = Decimal(int(total))
    fraction = total - integer_part
    if fraction < Decimal('0.50'):
        rounded = integer_part.quantize(CENT)
    else:
        rounded = (integer_part + Decimal('1.00')).quantize(CENT)
    round_off = (rounded - total).quantize(CENT)
    return rounded, round_off
