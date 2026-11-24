# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/receivers/SmsIngestionPipeline.kt

"""The live SMS -> transaction pipeline, shared by every ingestion entry
point: SimpleSMSReceiver (the real broadcast receiver) and, in debug builds
only, the debug injection tool. Keeping this in one place means the debug
injection exercises exactly the same code a real bank SMS would go through.

DEVIATION: Android collaborators become injected callables — the
LocalBroadcastManager broadcasts become `publish(event_name)`, the
PaymentResultActivity launch becomes `open_result(result)`, and
PaymentResultNotifier is `notifier.notify_result(result, post=...)`. The
result "intent extras" are a plain dict. Coroutine dispatch disappears
(synchronous port, see MIGRATION.md).
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from ..repository import TransactionRepository
from .detector import TransactionDetector
from .parser import SimpleTransaction

log = logging.getLogger("SmsIngestionPipeline")

# Event names carried over from the Android broadcasts.
EVENT_DISMISS_OVERLAY = "DISMISS_OVERLAY"
EVENT_SMS_RECEIVED = "com.paynet.app.SMS_RECEIVED"


def resolve_owner_txn_id(
    session_txn_id: Optional[str],
    window_txn_id: Optional[str],
    parsed: SimpleTransaction,
    adopt: Callable[[str], int],
) -> Optional[str]:
    """Decides which existing row (if any) owns this confirmation:
    - a live session claimed it -> that session's row;
    - no live session but the operation window recorded a session txnId and
      this is an outgoing-debit confirmation -> adopt that row (returns the
      id when adopt actually updated a row);
    - otherwise None -> caller inserts a standalone record.

    A CREDIT can never adopt: the recorded row is always an outgoing DEBIT.
    Pure decision logic — unit-tested with a fake adopt."""
    if session_txn_id is not None:
        return session_txn_id
    if window_txn_id is None or parsed.transaction_type == "CREDIT":
        return None
    try:
        updated = adopt(window_txn_id)
    except Exception:
        log.exception("Adopting orphaned row failed")
        updated = 0
    if updated > 0:
        log.debug("Confirmation reattached to orphaned session row")
        return window_txn_id
    return None


def is_unrelated_incoming_credit(
    record_txn_id: Optional[str], parsed: SimpleTransaction
) -> bool:
    """True when this ingestion is an incoming CREDIT that no payment
    claimed — an unrelated bank alert that only coincided with the operation
    window and must not surface a result screen or be persisted as a
    payment.

    A CREDIT can never legitimately own a row here: PaymentSessionManager's
    on_sms_confirmed rejects a CREDIT (a session is always an outgoing
    DEBIT) and resolve_owner_txn_id refuses to adopt one, so record_txn_id
    is always None for a CREDIT. The None check is kept explicit so that if
    a future owning path ever does claim one, it is surfaced rather than
    silently dropped. Pure — unit-tested."""
    return record_txn_id is None and parsed.transaction_type == "CREDIT"


def build_result(record_txn_id: Optional[str], transaction: SimpleTransaction) -> dict:
    """The result payload (Android's PaymentResultActivity intent extras)."""
    return {
        "transaction_id": record_txn_id or transaction.transaction_id,
        "amount": transaction.amount,
        "status": transaction.status,
        "bank_name": transaction.bank_name,
        "message": transaction.sms_excerpt,
        "timestamp": transaction.timestamp,
        "upi_id": transaction.upi_id,
        "transaction_type": transaction.transaction_type,
        "recipient_name": transaction.recipient_name,
        "phone_number": transaction.phone_number,
    }


def ingest(
    detector: TransactionDetector,
    sender: str,
    body: str,
    *,
    session_manager=None,
    repository: Optional[TransactionRepository] = None,
    publish: Optional[Callable[[str], None]] = None,
    notifier=None,
    open_result: Optional[Callable[[dict], None]] = None,
    clock: Callable[[], int] = lambda: int(time.time() * 1000),
) -> Optional[SimpleTransaction]:
    """Process one candidate bank SMS end to end. Returns the parsed
    transaction when it was a transaction SMS (even an ignored unrelated
    credit), else None."""
    # Captured BEFORE process_sms: a consuming match clears the operation
    # window (including this id).
    window_txn_id = detector.get_session_txn_id()

    transaction = detector.process_sms(sender, body)
    if transaction is None:
        log.debug("Not a transaction SMS")
        return None

    # An active payment session owns its row — update it in place. With no
    # live session (QR flow, or the process died mid-payment), try to
    # reattach the confirmation to the still-PENDING row recorded at
    # begin(); only insert a fresh row when neither applies. Without the
    # reattach, a payment whose process died would end up as TWO rows: a
    # fresh SUCCESS plus the original row. A confirmation arriving after the
    # deadline discarded that row finds nothing to adopt and is saved
    # standalone — the payment still surfaces.
    session_txn_id = None
    if session_manager is not None:
        session_txn_id = session_manager.on_sms_confirmed(transaction)

    def adopt(orphan_id: str) -> int:
        if repository is None:
            return 0
        return repository.confirm_transaction(
            transaction_id=orphan_id,
            status=transaction.status,
            parsed=transaction,
            verified_at=clock(),
        )

    record_txn_id = resolve_owner_txn_id(
        session_txn_id=session_txn_id,
        window_txn_id=window_txn_id,
        parsed=transaction,
        adopt=adopt,
    )

    # A stray incoming CREDIT that no payment claimed is an unrelated bank
    # alert (salary, refund, someone paying you) that merely arrived inside
    # the operation window — it is never a confirmation of our outgoing
    # DEBIT. Surfacing it would flash a false "Payment successful" result
    # screen for the credit's amount, post a success notification, and save
    # a phantom row, all while the real payment is still pending. Ignore it;
    # process_sms deliberately left the window open for the genuine debit.
    if is_unrelated_incoming_credit(record_txn_id, transaction):
        log.debug("Unrelated incoming credit during payment window - ignored")
        return transaction

    if record_txn_id is None and repository is not None:
        repository.save_transaction(transaction)
        log.debug("Transaction saved (no session, no adoptable row)")

    # Dismiss the USSD overlay (QR flow) and notify listening screens.
    if publish is not None:
        publish(EVENT_DISMISS_OVERLAY)
        publish(EVENT_SMS_RECEIVED)

    result = build_result(record_txn_id, transaction)
    # Notification first (also serves as a receipt), then the direct launch
    # — which can be silently blocked without the overlay permission; the
    # notification is the guaranteed-reachable path.
    if notifier is not None:
        notifier(result)
    if open_result is not None:
        open_result(result)

    return transaction
