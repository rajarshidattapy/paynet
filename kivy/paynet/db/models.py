# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/data/{Transaction,PaymentDetails,
# PaymentStatus,UPIData}.kt

"""Transaction domain models. Field-for-field ports of the Room entity and
the UI-facing PaymentDetails, keeping the exact status-mapping semantics."""

import enum
import re
from dataclasses import dataclass
from typing import Optional

from paynet import status as txn_status


class PaymentStatus(enum.Enum):
    """Lifecycle status attached to a payment record, mirroring the canonical
    status strings. UNVERIFIED and NEEDS_REVIEW are distinct from PENDING on
    purpose — collapsing them would hide the two outcomes the user most
    needs to see."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNVERIFIED = "UNVERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def _title_words(name: str) -> str:
    def _fix(match):
        word = match.group(0).lower()
        return word[:1].upper() + word[1:]

    return _WORD_RE.sub(_fix, name)


@dataclass
class PaymentDetails:
    """UI-facing payment transaction details."""

    id: str
    phoneNumber: str
    amount: float
    timestamp: int
    status: PaymentStatus
    recipientName: Optional[str] = None
    userConfirmed: Optional[bool] = None
    amountRecorded: bool = True

    @property
    def recipient_label(self) -> Optional[str]:
        if self.recipientName and self.recipientName.strip():
            return self.recipientName.strip()
        if self.phoneNumber.strip():
            return self.phoneNumber.strip()
        return None


@dataclass
class UPIData:
    vpa: str
    payeeName: str
    amount: str
    transactionNote: str
    currency: str


@dataclass
class Transaction:
    """A transaction row. Column names in the DB match the Room schema
    (transactionId, bankName, smsExcerpt, ...); the Python attribute names
    use the same camelCase so the mapping is one-to-one."""

    transactionId: str
    amount: str
    status: str
    bankName: str
    # Privacy-safe summary from parsed fields; never stores the raw SMS body.
    smsExcerpt: str
    timestamp: int = 0
    upiId: Optional[str] = None
    transactionType: str = "DEBIT"
    recipientName: Optional[str] = None
    phoneNumber: Optional[str] = None
    bankRef: Optional[str] = None
    deadlineAt: Optional[int] = None
    source: Optional[str] = None
    verifiedAt: Optional[int] = None

    COLUMNS = (
        "transactionId", "amount", "status", "bankName", "smsExcerpt",
        "timestamp", "upiId", "transactionType", "recipientName",
        "phoneNumber", "bankRef", "deadlineAt", "source", "verifiedAt",
    )

    @property
    def display_recipient(self) -> Optional[str]:
        if self.recipientName is None:
            return None
        name = self.recipientName.strip()
        if not name:
            return None
        if "@" in name or not any(c.isalpha() for c in name):
            return name
        return _title_words(name)

    @property
    def recipient_label(self) -> Optional[str]:
        """The same identity fallback is used by every transaction surface."""
        if self.display_recipient:
            return self.display_recipient
        if self.phoneNumber and self.phoneNumber.strip():
            return self.phoneNumber.strip()
        if self.upiId and self.upiId.strip():
            return self.upiId.strip()
        return None

    def to_payment_details(self) -> PaymentDetails:
        status_upper = self.status.upper()
        if self.status == "USER_CONFIRMED":
            user_confirmed = True
        elif self.status == "USER_NOT_CONFIRMED":
            user_confirmed = False
        else:
            user_confirmed = None

        if status_upper in ("SUCCESS", "SUCCESSFUL", "COMPLETED"):
            status = PaymentStatus.COMPLETED
        elif status_upper in ("UNVERIFIED", "USER_CONFIRMED", "USER_NOT_CONFIRMED"):
            status = PaymentStatus.UNVERIFIED
        elif status_upper == "NEEDS_REVIEW":
            status = PaymentStatus.NEEDS_REVIEW
        elif status_upper == "PENDING":
            status = PaymentStatus.PENDING
        elif status_upper == "CANCELLED":
            status = PaymentStatus.CANCELLED
        elif status_upper in ("FAILED", "DECLINED"):
            status = PaymentStatus.FAILED
        else:
            status = PaymentStatus.PENDING

        try:
            amount = float(self.amount)
        except (TypeError, ValueError):
            amount = 0.0

        return PaymentDetails(
            id=self.transactionId,
            recipientName=self.recipient_label,
            phoneNumber=self.phoneNumber or "",
            amount=amount,
            timestamp=self.timestamp,
            amountRecorded=bool(self.amount and self.amount.strip()),
            userConfirmed=user_confirmed,
            status=status,
        )

    @staticmethod
    def from_simple_transaction(simple_transaction) -> "Transaction":
        return Transaction(
            transactionId=simple_transaction.transaction_id,
            amount=simple_transaction.amount,
            status=simple_transaction.status,
            bankName=simple_transaction.bank_name,
            smsExcerpt=simple_transaction.sms_excerpt,
            timestamp=simple_transaction.timestamp,
            upiId=simple_transaction.upi_id,
            transactionType=simple_transaction.transaction_type,
            recipientName=simple_transaction.recipient_name,
            phoneNumber=simple_transaction.phone_number,
            bankRef=simple_transaction.transaction_id,
            source=txn_status.SOURCE_SMS,
        )
