# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/utils/CurrencyFormat.kt

"""One place that decides how a rupee amount is grouped.

Implements the Indian 3-2-2 grouping explicitly (Rs 1,00,000.00) rather
than delegating to locale data, so the result is identical on every device
and in CI. Rounds HALF_EVEN to two places, matching the Kotlin original.

Returns digits only — callers supply the ₹ symbol.
"""

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

LAST_GROUP = 3    # digits in the rightmost group
HIGHER_GROUPS = 2  # digits in every group above it
FRACTION_DIGITS = 2


def inr(amount) -> str:
    """Group an amount Indian-style.

    Returns the input unchanged when it isn't a number — a bank template
    this parser didn't fully understand must still show the user whatever
    it did capture, never an error, a blank, or a fabricated 0.00.
    """
    if isinstance(amount, Decimal):
        value = amount
    else:
        try:
            value = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            return amount if isinstance(amount, str) else str(amount)
    return _format(value)


def _format(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    sign = "-" if rounded < 0 else ""
    whole, _, fraction = f"{abs(rounded):.2f}".partition(".")
    return f"{sign}{_group_indian(whole)}.{fraction}"


def _group_indian(digits: str) -> str:
    """'1234567' -> '12,34,567'. Three at the end, then twos."""
    if len(digits) <= LAST_GROUP:
        return digits
    groups = [digits[-LAST_GROUP:]]
    rest = digits[:-LAST_GROUP]
    while len(rest) > HIGHER_GROUPS:
        groups.insert(0, rest[-HIGHER_GROUPS:])
        rest = rest[:-HIGHER_GROUPS]
    if rest:
        groups.insert(0, rest)
    return ",".join(groups)
