# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/payment/InvalidReasonMessages.kt

"""The UI edge where a validation Reason becomes a sentence a user reads.

Copy mirrors app/src/main/res/values/strings.xml. The two amount messages
take their numbers from paynet/constants.py rendered through
paynet/utils/currency.py, so the ceiling quoted to the user cannot drift
from the ceiling actually enforced.
"""

from paynet import constants
from paynet.payment.call_string import Reason
from paynet.utils.currency import inr

_MESSAGES = {
    Reason.SERVICE_NUMBER: "The UPI service number is not valid.",
    Reason.RECIPIENT_NUMBER: "Enter a valid 10-digit phone number.",
    Reason.AMOUNT_NOT_WHOLE_RUPEES: (
        "Enter a whole rupee amount — the IVR cannot dial paise."
    ),
    Reason.AMOUNT_NOT_A_NUMBER: "Enter a valid amount.",
}


def message_for(reason: Reason) -> str:
    if reason is Reason.AMOUNT_BELOW_MINIMUM:
        return f"Minimum ₹{inr(constants.MIN_AMOUNT_VALUE)} per payment."
    if reason is Reason.AMOUNT_ABOVE_CAP:
        return (
            f"Maximum ₹{inr(constants.UPI123PAY_MAX_AMOUNT)} per payment — "
            "the UPI 123Pay IVR rejects anything above this."
        )
    return _MESSAGES[reason]
