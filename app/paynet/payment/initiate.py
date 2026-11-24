# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from the initiateTransfer/canInitiateTransfer/isTransferInputValid
# block of app/src/main/java/com/paynet/app/helpers/MainActivityHelper.kt.

"""The transfer-initiation gate the pay-contact and QR flows share.

DEVIATION (device-only, recorded in MIGRATION.md): the Kotlin gates on
RECEIVE_SMS / phone / overlay permissions and then places a real UPI 123PAY
IVR call through CallManager; neither is possible or permitted off-device.
The port validates input, enforces the UPI123-enabled gate and opens the
payment session (the PENDING row), and hands actual call placement to an
injected callable that stays None until the Android telephony layer exists.
"""

import logging
from typing import Callable, Optional

from paynet import constants
from paynet.payment import validation
from paynet.payment.call_string import Reason
from paynet.payment.messages import message_for

log = logging.getLogger(__name__)

# strings.xml
STR_ENTER_PHONE_AND_AMOUNT = "Enter both a phone number and an amount."
STR_INVALID_PHONE = "Enter a valid 10-digit phone number."
STR_INVALID_AMOUNT = "Enter a valid amount."
STR_PAYMENT_NOT_STARTED = "Payment could not be started. Try again."


class TransferInitiator:
    def __init__(
        self,
        test_results,
        session_manager,
        show_toast: Callable[[str], None],
        on_setup_required: Callable[[], None] = lambda: None,
        place_call: Optional[Callable[[str, str], bool]] = None,
    ) -> None:
        self._test_results = test_results
        self._session_manager = session_manager
        self._show_toast = show_toast
        self._on_setup_required = on_setup_required
        self._place_call = place_call

    def is_transfer_input_valid(self, phone_number: str, amount: str) -> bool:
        if not phone_number.strip() or not amount.strip():
            self._show_toast(STR_ENTER_PHONE_AND_AMOUNT)
            return False
        if not validation.is_valid_phone_number(phone_number):
            self._show_toast(STR_INVALID_PHONE)
            return False
        try:
            amount_value = float(amount)
        except ValueError:
            amount_value = None
        if amount_value is None or amount_value < constants.MIN_AMOUNT_VALUE:
            self._show_toast(STR_INVALID_AMOUNT)
            return False
        if amount_value > constants.UPI123PAY_MAX_AMOUNT:
            # Same reason, same wording as the one the call-string builder
            # raises further down the path.
            self._show_toast(message_for(Reason.AMOUNT_ABOVE_CAP))
            return False
        return True

    def can_initiate_transfer(self, phone_number: str, amount: str) -> bool:
        if not self.is_transfer_input_valid(phone_number, amount):
            return False
        results = self._test_results.get_test_results()
        if not (results and results.upi123Enabled):
            # Kotlin: navigateToTestConfiguration().
            self._on_setup_required()
            return False
        # DEVIATION: RECEIVE_SMS / phone / overlay permission gates are
        # device-only and unverified from the desktop (MIGRATION.md).
        return True

    def initiate_transfer(
        self,
        phone_number: str,
        amount: str,
        recipient_name: Optional[str] = None,
    ) -> Optional[str]:
        """Opens the payment session; returns the new transaction id, or
        None when a gate refused. begin() always succeeds — a new payment
        supersedes any session still in flight rather than being refused."""
        if not self.can_initiate_transfer(phone_number, amount):
            return None
        if self._session_manager is None:
            log.error("PaymentSessionManager unavailable")
            self._show_toast(STR_PAYMENT_NOT_STARTED)
            return None
        transaction_id = self._session_manager.begin(
            phone_number, amount, recipient_name=recipient_name)
        # DEVIATION: TransactionDetector.startOperation, the IVR call itself
        # and the call overlay are device-only. When a telephony layer is
        # supplied it places the call; the desktop build never dials.
        if self._place_call is not None:
            self._place_call(phone_number, amount)
        return transaction_id
