# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/payment/PaymentSessionManager.kt

"""The only writer of payment lifecycle state.

A manual UPI 123Pay transfer flows through here:
 1. begin() inserts a PENDING row *before* anything is dialled, so the
    database always knows a payment was attempted — even if the process
    dies mid-call.
 2. Call activity (from the CallStateCoordinator) moves the in-memory
    PaymentState: OFFHOOK -> InProgress, short hang-up -> Cancelled,
    normal call end -> WaitingForVerification.
 3. A confirming bank SMS (on_sms_confirmed) is the only path to SUCCESS.
    Call duration is never treated as proof of payment.
 4. If no SMS arrives before the deadline the row is discarded. A payment
    the bank never confirmed is one this app cannot report on, so it
    leaves no record rather than an outcome the user can't act on.

DEVIATION FROM THE KOTLIN (recorded in MIGRATION.md): the original runs on
coroutines — the PENDING insert and every terminal write are fire-and-forget
on a scope, and on_sms_confirmed/finish_session/on_verification_deadline must
join pendingInsertJob before writing so a fast confirmation cannot beat the
insert. This port writes SYNCHRONOUSLY: begin() does not return until the
PENDING row exists, so the join invariant is satisfied by construction and
the race the @Volatile pendingInsertJob guarded against cannot occur. The
claim-first-then-write invariants are preserved exactly: the terminal state
is claimed inside the session lock and ONLY the claiming caller writes.

The verification watchdog is a threading.Timer by default; tests inject a
manual scheduler for deterministic deadlines.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, List, Optional, Protocol

from ..db.models import Transaction
from ..sms.parser import SimpleTransaction
from ..telephony.coordinator import CallSessionEvent, Ended, Started
from . import state as ps
from .state import PaymentState

log = logging.getLogger("PaymentSessionManager")

# TransactionStatus / TransactionSource constants (paynet.status values).
STATUS_PENDING = "PENDING"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"
STATUS_CANCELLED = "CANCELLED"
STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"
SOURCE_MANUAL = "MANUAL"

DEFAULT_VERIFICATION_DEADLINE_MS = 10 * 60 * 1000  # 10 minutes
DEFAULT_MIN_REAL_CALL_DURATION_MS = 5_000
_COORDINATOR_TAG = "payment-session"


class PaymentTransactionStore(Protocol):
    """Minimal persistence surface the session manager needs. Implemented by
    TransactionRepository; faked in unit tests."""

    def insert_pending(self, transaction: Transaction) -> None:
        ...

    def transition_status(
        self, transaction_id: str, expected_status: str, new_status: str
    ) -> int:
        """Atomically move a row from expected_status to new_status.
        Returns rows changed."""
        ...

    def confirm_transaction(
        self, transaction_id: str, status: str, parsed: SimpleTransaction, verified_at: int
    ) -> int:
        """Fill in bank-confirmed details on the session row. Returns rows
        changed."""
        ...

    def delete_stale_pending(self, now: int) -> int:
        """Discards PENDING rows past their deadline. Returns rows removed."""
        ...

    def delete_pending(self, transaction_id: str) -> int:
        """Discards one row, only while it is still PENDING. Returns rows
        removed."""
        ...


class WatchdogHandle(Protocol):
    def cancel(self) -> None:
        ...


class _TimerHandle:
    def __init__(self, timer: threading.Timer) -> None:
        self._timer = timer

    def cancel(self) -> None:
        self._timer.cancel()


def _timer_watchdog(delay_ms: int, callback: Callable[[], None]) -> WatchdogHandle:
    timer = threading.Timer(delay_ms / 1000.0, callback)
    timer.daemon = True
    timer.start()
    return _TimerHandle(timer)


class PaymentSessionManager:
    def __init__(
        self,
        store: PaymentTransactionStore,
        coordinator,
        clock: Callable[[], int] = lambda: int(time.time() * 1000),
        verification_deadline_ms: int = DEFAULT_VERIFICATION_DEADLINE_MS,
        min_real_call_duration_ms: int = DEFAULT_MIN_REAL_CALL_DURATION_MS,
        watchdog_factory: Callable[[int, Callable[[], None]], WatchdogHandle] = _timer_watchdog,
    ) -> None:
        self._store = store
        self._coordinator = coordinator
        self._clock = clock
        self._verification_deadline_ms = verification_deadline_ms
        self._min_real_call_duration_ms = min_real_call_duration_ms
        self._watchdog_factory = watchdog_factory

        self._payment_state: PaymentState = ps.IDLE
        self._state_listeners: List[Callable[[PaymentState], None]] = []

        # One lock guards every state read/claim. RLock because listeners
        # notified from _set_state run before the lock is released and may
        # legitimately re-read the manager (never block in a listener).
        self._session_lock = threading.RLock()
        self._unsubscribe_session_events: Optional[Callable[[], None]] = None
        self._watchdog: Optional[WatchdogHandle] = None
        self._coordinator_acquired = False

    # ---- observable state (StateFlow replacement) -------------------------

    @property
    def payment_state(self) -> PaymentState:
        with self._session_lock:
            return self._payment_state

    def subscribe(self, listener: Callable[[PaymentState], None]) -> Callable[[], None]:
        """Observe state changes; returns an unsubscribe handle. Listeners
        run synchronously on the mutating thread before the session lock is
        released — they must not block."""
        with self._session_lock:
            self._state_listeners.append(listener)

        def unsubscribe() -> None:
            with self._session_lock:
                if listener in self._state_listeners:
                    self._state_listeners.remove(listener)

        return unsubscribe

    def _set_state(self, new_state: PaymentState) -> None:
        """Caller must hold _session_lock."""
        self._payment_state = new_state
        for listener in list(self._state_listeners):
            listener(new_state)

    # ---- lifecycle ----------------------------------------------------------

    def begin(
        self,
        phone_number: str,
        amount: str,
        upi_id: Optional[str] = None,
        source: str = SOURCE_MANUAL,
        recipient_name: Optional[str] = None,
    ) -> str:
        """Starts a new payment session and records a PENDING row. Always
        succeeds.

        A new payment SUPERSEDES any session still in flight. Refusing used
        to strand the user: a session the bank never confirmed stayed in
        progress for its full verification deadline and blocked every retry.
        Superseding is safe because a session is not what decides an outcome
        — the bank's SMS is. The superseded PENDING row is discarded (under
        "no confirmation, no record" it must leave no trace)."""
        with self._session_lock:
            previous = self._payment_state
            superseded_txn_id: Optional[str] = None
            if previous.is_in_progress():
                log.warning("begin() supersedes the session still in flight")
                self._cleanup_locked()
                superseded_txn_id = previous.get_transaction_id()
            initiating = ps.Initiating(phone_number, amount)
            self._set_state(initiating)
            if not self._coordinator_acquired:
                self._coordinator.acquire(_COORDINATOR_TAG)
                self._coordinator_acquired = True

        txn_id = initiating.transactionId
        now = self._clock()
        deadline_at = now + self._verification_deadline_ms

        # Drop the superseded row. delete_pending is guarded to PENDING, so a
        # confirmation that landed on it a moment earlier is never erased.
        # Synchronous: no pending-insert race exists in this port.
        if superseded_txn_id is not None:
            self._store.delete_pending(superseded_txn_id)

        # Older stale sessions are discarded before a new one starts.
        try:
            self._store.delete_stale_pending(now)
        except Exception:
            log.exception("deleteStalePending failed during begin()")
        self._store.insert_pending(
            Transaction(
                transactionId=txn_id,
                amount=amount,
                status=STATUS_PENDING,
                bankName="",
                smsExcerpt="",
                timestamp=now,
                transactionType="DEBIT",
                phoneNumber=phone_number,
                recipientName=recipient_name,
                upiId=upi_id,
                deadlineAt=deadline_at,
                source=source,
            )
        )
        log.debug("PENDING row recorded for session")

        self._unsubscribe_session_events = self._coordinator.add_session_listener(
            self._on_call_session_event
        )
        self._watchdog = self._watchdog_factory(
            self._verification_deadline_ms, self._on_verification_deadline
        )

        log.debug("Payment session started")
        return txn_id

    def on_dial_failed(self, reason: str) -> None:
        """The dial intent could not be launched; the session never really
        started."""
        self._finish_session(
            STATUS_CANCELLED,
            lambda phone, amount, txn_id: ps.Cancelled(phone, amount, txn_id, reason),
        )

    def on_user_cancelled(self) -> None:
        """The user aborted from the in-call overlay. Safe to invoke more
        than once (CallOverlayService calls it before any cleanup that could
        throw, and again from its catch block)."""
        self._finish_session(
            STATUS_CANCELLED,
            lambda phone, amount, txn_id: ps.Cancelled(phone, amount, txn_id, "Cancelled by user"),
        )

    def on_call_never_started(self) -> None:
        """The dial intent launched but no call ever went OFFHOOK (watchdog
        from the overlay service). Only acts while still Initiating."""
        with self._session_lock:
            if not isinstance(self._payment_state, ps.Initiating):
                return
        self._finish_session(
            STATUS_CANCELLED,
            lambda phone, amount, txn_id: ps.Cancelled(
                phone, amount, txn_id, "The payment call was never connected"
            ),
        )

    def on_sms_confirmed(self, parsed: SimpleTransaction) -> Optional[str]:
        """A parsed bank SMS arrived. If a session is active, its row is
        updated in place and the session transaction id is returned; callers
        must NOT insert a separate row in that case. Returns None when no
        session was active (e.g. the QR flow), letting callers fall back to
        their own persistence."""
        # Direction check: a manual session is always an outgoing DEBIT
        # (begin() inserts transactionType = "DEBIT"), so an incoming CREDIT
        # SMS can never confirm it. Returning None lets the caller fall back
        # to standalone persistence, exactly like the QR/no-session flow.
        if parsed.transaction_type == "CREDIT":
            log.debug("CREDIT SMS during DEBIT session - not a confirmation")
            return None

        if parsed.status.upper() == STATUS_FAILED:
            new_status = STATUS_FAILED
        elif parsed.status.upper() == STATUS_NEEDS_REVIEW:
            new_status = STATUS_NEEDS_REVIEW
        else:
            new_status = STATUS_SUCCESS
        verified_at = self._clock()

        # Check-and-claim is ONE atomic step: claiming inside a single lock
        # guarantees exactly one caller ever owns the confirmation, so two
        # near-simultaneous SMS can never both write a terminal outcome.
        with self._session_lock:
            current = self._payment_state
            if not current.is_in_progress():
                return None
            txn_id = current.get_transaction_id()
            if txn_id is None:
                return None
            phone = current.get_phone_number() or parsed.phone_number or ""
            amount = current.get_amount() or parsed.amount

            if new_status == STATUS_FAILED:
                terminal: PaymentState = ps.Failed(
                    error="Bank reported the payment as failed",
                    phoneNumber=phone,
                    amount=amount,
                    transactionId=txn_id,
                    canRetry=True,
                )
            elif new_status == STATUS_NEEDS_REVIEW:
                terminal = ps.NeedsReview(
                    transactionId=txn_id, phoneNumber=phone, amount=amount
                )
            else:
                terminal = ps.Success(
                    transactionId=txn_id,
                    phoneNumber=phone,
                    amount=amount,
                    bankReference=parsed.transaction_id,
                    timestamp=verified_at,
                )
            self._set_state(terminal)
            self._cleanup_locked()

        updated = self._store.confirm_transaction(
            transaction_id=txn_id,
            status=new_status,
            parsed=parsed,
            verified_at=verified_at,
        )
        log.debug("Session row confirmed as %s (rows=%d)", new_status, updated)
        return txn_id

    def acknowledge_result(self) -> None:
        """UI acknowledges a terminal result and returns the session to Idle."""
        with self._session_lock:
            state = self._payment_state
            if state.is_terminal() or isinstance(state, ps.Timeout):
                self._set_state(ps.IDLE)

    def reconcile_stale_pending(self) -> None:
        """Discards PENDING rows whose deadline passed while we weren't
        running."""
        try:
            discarded = self._store.delete_stale_pending(self._clock())
        except Exception:
            discarded = 0
        if discarded > 0:
            log.debug("Discarded %d unconfirmed stale PENDING transaction(s)", discarded)

    # ---- call events --------------------------------------------------------

    def _on_call_session_event(self, event: CallSessionEvent) -> None:
        if isinstance(event, Started):
            with self._session_lock:
                state = self._payment_state
                if isinstance(state, ps.Initiating):
                    self._set_state(
                        ps.InProgress(
                            step="On the line with the UPI service",
                            progress=0.4,
                            phoneNumber=state.phoneNumber,
                            amount=state.amount,
                            transactionId=state.transactionId,
                        )
                    )
        elif isinstance(event, Ended):
            with self._session_lock:
                state = self._payment_state
            if isinstance(state, ps.InProgress) and event.duration_ms < self._min_real_call_duration_ms:
                self._finish_session(
                    STATUS_CANCELLED,
                    lambda phone, amount, txn_id: ps.Cancelled(
                        phone,
                        amount,
                        txn_id,
                        "Call ended before the payment flow could complete",
                    ),
                )
            elif isinstance(state, ps.InProgress):
                with self._session_lock:
                    # Re-check: an SMS may have confirmed while we were deciding.
                    s = self._payment_state
                    if isinstance(s, ps.InProgress):
                        self._set_state(
                            ps.WaitingForVerification(
                                timeout=self._verification_deadline_ms,
                                phoneNumber=s.phoneNumber,
                                amount=s.amount,
                                transactionId=s.transactionId,
                            )
                        )
            # else: Initiating without OFFHOOK, or already terminal — nothing to do.

    # ---- terminal transitions -------------------------------------------------

    def _on_verification_deadline(self) -> None:
        """The deadline passed with no confirming bank SMS, so the row is
        discarded and nothing is shown: no confirmation means no payment to
        report. A genuine confirmation arriving in the SMS window's remaining
        grace still surfaces — with the row gone there is nothing to adopt,
        so the ingestion pipeline records it as a standalone transaction.

        Claim FIRST, write second: only the winner writes."""
        with self._session_lock:
            s = self._payment_state
            if not s.is_in_progress():
                return
            txn_id = s.get_transaction_id()
            if txn_id is None:
                return
            self._set_state(
                ps.Timeout(
                    timeoutType=ps.TimeoutType.BANK_VERIFICATION,
                    phoneNumber=s.get_phone_number() or "",
                    amount=s.get_amount() or "",
                    transactionId=txn_id,
                )
            )
            self._cleanup_locked()

        self._store.delete_pending(txn_id)
        log.warning("No bank SMS before deadline - unconfirmed session discarded")

    def _finish_session(
        self,
        row_status: str,
        terminal_state: Callable[[str, str, str], PaymentState],
    ) -> None:
        """Claim FIRST, write second — same invariant as on_sms_confirmed.
        Only the caller that actually claims the terminal state may write,
        so a cancel landing at the same instant as the bank's SMS can never
        leave history contradicting the screen."""
        with self._session_lock:
            s = self._payment_state
            if not s.is_in_progress():
                return
            txn_id = s.get_transaction_id()
            if txn_id is None:
                return
            self._set_state(
                terminal_state(s.get_phone_number() or "", s.get_amount() or "", txn_id)
            )
            self._cleanup_locked()

        self._store.transition_status(txn_id, STATUS_PENDING, row_status)

    def _cleanup_locked(self) -> None:
        """Caller must hold _session_lock."""
        if self._unsubscribe_session_events is not None:
            self._unsubscribe_session_events()
            self._unsubscribe_session_events = None
        if self._watchdog is not None:
            self._watchdog.cancel()
            self._watchdog = None
        if self._coordinator_acquired:
            self._coordinator.release(_COORDINATOR_TAG)
            self._coordinator_acquired = False
