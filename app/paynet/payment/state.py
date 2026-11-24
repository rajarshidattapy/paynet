# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/states/PaymentState.kt
# and app/src/main/java/com/paynet/app/payment/QrWaitingState.kt

"""Payment lifecycle state hierarchy.

Kotlin's sealed class hierarchy becomes one dataclass per state; Idle is a
singleton instance (Kotlin `object`). All helper semantics are 1:1 with
PaymentState.kt: is_terminal, is_in_progress, can_retry, the id/phone/amount
accessors, display message, and progress percentage.
"""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


class TimeoutType(enum.Enum):
    CALL_INITIATION = "CALL_INITIATION"
    BANK_VERIFICATION = "BANK_VERIFICATION"
    USER_RESPONSE = "USER_RESPONSE"
    NETWORK_CONNECTION = "NETWORK_CONNECTION"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_txn_id() -> str:
    return str(uuid.uuid4())


class PaymentState:
    """Base class for the payment state hierarchy (Kotlin sealed class)."""

    def is_terminal(self) -> bool:
        return isinstance(self, (Success, Failed, Cancelled, NeedsReview))

    def is_in_progress(self) -> bool:
        return isinstance(self, (Initiating, InProgress, WaitingForVerification))

    def can_retry(self) -> bool:
        if isinstance(self, Failed):
            return self.canRetry
        if isinstance(self, Timeout):
            return True
        return False

    def get_transaction_id(self) -> Optional[str]:
        return getattr(self, "transactionId", None)

    def get_phone_number(self) -> Optional[str]:
        return getattr(self, "phoneNumber", None)

    def get_amount(self) -> Optional[str]:
        return getattr(self, "amount", None)

    def get_display_message(self) -> str:
        if isinstance(self, Idle):
            return "Ready to make payment"
        if isinstance(self, Initiating):
            return "Initiating payment..."
        if isinstance(self, InProgress):
            return f"Processing: {self.step}"
        if isinstance(self, WaitingForVerification):
            return "Waiting for bank verification..."
        if isinstance(self, Success):
            return "Payment successful!"
        if isinstance(self, Failed):
            return f"Payment failed: {self.error}"
        if isinstance(self, NeedsReview):
            return "Payment needs review — check your bank statement"
        if isinstance(self, Cancelled):
            return f"Payment cancelled: {self.reason}"
        if isinstance(self, Timeout):
            return f"Payment timeout: {self.timeoutType.name}"
        raise TypeError(f"unknown PaymentState: {self!r}")

    def get_progress_percentage(self) -> float:
        if isinstance(self, Idle):
            return 0.0
        if isinstance(self, Initiating):
            return 0.1
        if isinstance(self, InProgress):
            return self.progress
        if isinstance(self, WaitingForVerification):
            return 0.7
        if isinstance(self, (Success, NeedsReview)):
            return 1.0
        return 0.0  # Failed, Cancelled, Timeout


class Idle(PaymentState):
    """Kotlin `object Idle` — instantiate once; module-level IDLE below."""

    _instance: Optional["Idle"] = None

    def __new__(cls) -> "Idle":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "PaymentState.Idle"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Idle)

    def __hash__(self) -> int:
        return hash(Idle)


IDLE = Idle()


@dataclass
class Initiating(PaymentState):
    phoneNumber: str
    amount: str
    transactionId: str = field(default_factory=_new_txn_id)


@dataclass
class InProgress(PaymentState):
    step: str
    progress: float
    phoneNumber: str
    amount: str
    transactionId: str


@dataclass
class WaitingForVerification(PaymentState):
    timeout: int
    phoneNumber: str
    amount: str
    transactionId: str


@dataclass
class Success(PaymentState):
    transactionId: str
    phoneNumber: str
    amount: str
    bankReference: Optional[str] = None
    timestamp: int = field(default_factory=_now_ms)


@dataclass
class Failed(PaymentState):
    error: str
    phoneNumber: str
    amount: str
    transactionId: str
    errorCode: Optional[str] = None
    canRetry: bool = True


@dataclass
class NeedsReview(PaymentState):
    transactionId: str
    phoneNumber: str
    amount: str


@dataclass
class Cancelled(PaymentState):
    phoneNumber: str
    amount: str
    transactionId: str
    reason: str = "User cancelled"


@dataclass
class Timeout(PaymentState):
    timeoutType: TimeoutType
    phoneNumber: str
    amount: str
    transactionId: str


def should_close_qr_waiting_screen(
    transaction_id: Optional[str], state: PaymentState
) -> bool:
    """A deadline ends the waiting UI without asserting a bank outcome or
    closing the SMS grace window. 1:1 with QrWaitingState.kt."""
    return (
        transaction_id is not None
        and state.get_transaction_id() == transaction_id
        and (state.is_terminal() or isinstance(state, Timeout))
    )
