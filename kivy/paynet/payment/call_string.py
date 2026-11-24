# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/payment/Upi123CallStringBuilder.kt

"""Builds the DTMF-encoded dial string for the UPI 123Pay IVR flow.

Format: tel:<serviceNumber>,,1,<phoneNumber>,,<amount>,,1
where "," is a 2-second dialer pause and the digits between pauses are
DTMF tones consumed by the IVR menu (1 = "send money", then recipient,
then amount, then 1 = confirm).

Intentionally pure (no Android/Kivy dependencies) so the exact dial string
is locked by unit tests — a malformed string here dials a wrong DTMF
sequence against a live payment IVR.
"""

import enum
import re
from dataclasses import dataclass

from paynet import constants

_SERVICE_NUMBER_REGEX = re.compile(r"^0?[1-9][0-9]{9,11}$")
_PHONE_REGEX = re.compile(constants.PHONE_NUMBER_PATTERN)
_WHOLE_RUPEES_REGEX = re.compile(r"^[0-9]{1,6}$")


class Reason(enum.Enum):
    """Why a dial string could not be built.

    An enum rather than an English sentence so this module stays free of
    user-facing copy; the message mapping lives at the UI edge
    (paynet/payment/messages.py).
    """

    SERVICE_NUMBER = enum.auto()
    RECIPIENT_NUMBER = enum.auto()
    AMOUNT_NOT_WHOLE_RUPEES = enum.auto()
    AMOUNT_NOT_A_NUMBER = enum.auto()
    AMOUNT_BELOW_MINIMUM = enum.auto()
    AMOUNT_ABOVE_CAP = enum.auto()


@dataclass(frozen=True)
class Valid:
    call_string: str


@dataclass(frozen=True)
class Invalid:
    reason: Reason


def build(service_number: str, phone_number: str, amount: str):
    """Return Valid(call_string) or Invalid(reason)."""
    service = "".join(c for c in service_number if c.isdigit())
    phone = "".join(c for c in phone_number if c.isdigit())
    rupees = amount.strip()

    if not _SERVICE_NUMBER_REGEX.fullmatch(service):
        return Invalid(Reason.SERVICE_NUMBER)
    if not _PHONE_REGEX.fullmatch(phone):
        return Invalid(Reason.RECIPIENT_NUMBER)
    # The IVR consumes whole-rupee DTMF digits; decimals cannot be dialled.
    if not _WHOLE_RUPEES_REGEX.fullmatch(rupees):
        return Invalid(Reason.AMOUNT_NOT_WHOLE_RUPEES)
    try:
        value = int(rupees)
    except ValueError:
        return Invalid(Reason.AMOUNT_NOT_A_NUMBER)
    if value < int(constants.MIN_AMOUNT_VALUE):
        return Invalid(Reason.AMOUNT_BELOW_MINIMUM)
    if value > int(constants.UPI123PAY_MAX_AMOUNT):
        return Invalid(Reason.AMOUNT_ABOVE_CAP)

    return Valid(f"tel:{service},,1,{phone},,{value},,1")
