# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/payment/PaymentInputValidator.kt

"""Pure validation of user-entered payment inputs — no Android/Kivy
dependencies, so it is directly unit-testable. The dial-string construction
that consumes these values is validated separately in
paynet/payment/call_string.py."""

import re

from paynet import constants

_PHONE_REGEX = re.compile(constants.PHONE_NUMBER_PATTERN)


def is_valid_phone_number(phone_number):
    """Exactly 10 digits, no leading zero."""
    if not phone_number or not phone_number.strip():
        return False
    return _PHONE_REGEX.fullmatch(phone_number) is not None


def is_valid_amount(amount):
    """A positive amount within the generic input range (Rs 1 ... Rs 1,00,000)."""
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return False
    return constants.MIN_AMOUNT_VALUE <= value <= constants.MAX_AMOUNT_VALUE
