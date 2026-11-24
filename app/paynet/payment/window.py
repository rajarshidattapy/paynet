# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/payment/PaymentWindowObserver.kt

"""Closes the SMS operation window when a payment is cancelled.

The window is TransactionDetector's record that a payment is in flight;
while it is open, an arriving bank SMS may be claimed as this payment's
confirmation. Cancelling used to end the *session* without closing the
*window*, leaving it armed for the rest of its 10.5-minute life — so a
later same-amount debit (the user re-paying through another app, say) was
adopted onto the cancelled row and flipped it to SUCCESS.

Every cancel route — the overlay's terminate button, the never-connected
watchdog, a call that ended before the IVR flow could finish, a failed
dial — funnels into PaymentSessionManager._finish_session and emits
PaymentState.Cancelled, so observing that one state closes them all.

Deliberately *not* triggered by Timeout: the window outlives the
verification deadline by 30 seconds on purpose, so a slow-but-genuine
confirmation still lands. Closing it at the deadline would discard an SMS
that did arrive. It expires on its own.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from .state import Cancelled, PaymentState

log = logging.getLogger("PaymentWindowObserver")


def should_disarm_sms_window(state: PaymentState) -> bool:
    """Pure mapping: only a cancelled session must also close the SMS window.
    Success and failure consume the window in the ingestion path, and a
    timeout leaves it to expire on its own."""
    return isinstance(state, Cancelled)


class PaymentWindowObserver:
    """Subscribes to a PaymentSessionManager and disarms the SMS window on
    Cancelled. The Android default disarm
    (TransactionDetector.getInstance(context).stopOperation()) is replaced
    by an injectable callback; feature 6 wires it to the detector."""

    def __init__(
        self,
        session_manager,
        on_disarm: Optional[Callable[[], None]] = None,
    ) -> None:
        self._session_manager = session_manager
        self._on_disarm = on_disarm or self._default_disarm
        self._unsubscribe: Optional[Callable[[], None]] = None

    def start(self) -> None:
        def observe(state: PaymentState) -> None:
            if should_disarm_sms_window(state):
                self._on_disarm()

        self._unsubscribe = self._session_manager.subscribe(observe)

    def stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    @staticmethod
    def _default_disarm() -> None:
        # Wired to TransactionDetector.stop_operation() in feature 6; until
        # then the observer requires an explicit on_disarm to do anything.
        log.debug("Payment cancelled - SMS operation window close requested")
