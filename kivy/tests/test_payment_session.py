# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/test/java/com/paynet/app/payment/PaymentSessionManagerTest.kt

"""The session manager is the only writer of payment lifecycle state, and
payment reality is defined exactly: only a confirming bank SMS (matched to
the amount, inside the active window) may mark a payment SUCCESS. Call state
and call duration never can. An unconfirmed attempt leaves no row behind.

DEVIATION FROM THE KOTLIN TESTS: the original drives coroutines on a test
scheduler (runCurrent/advanceTimeBy). This port is synchronous — begin()
returns only after the PENDING row exists, and terminal writes complete
before the confirming call returns — so no scheduler pumping is needed and
the pendingInsertJob-join tests are satisfied by construction. The
verification watchdog is a ManualWatchdog the tests fire explicitly. The two
real-thread race tests port directly (barrier + real threads).
"""

import threading

from paynet.db.models import Transaction
from paynet.payment import state as ps
from paynet.payment.session import PaymentSessionManager
from paynet.sms.parser import SimpleTransaction
from paynet.telephony.coordinator import DEVICE_IDLE, DEVICE_OFFHOOK, Ended, Started

PENDING = "PENDING"
SUCCESS = "SUCCESS"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
NEEDS_REVIEW = "NEEDS_REVIEW"


class FakeCallStateSource:
    def __init__(self):
        self.call_state = DEVICE_IDLE
        self.acquire_count = 0
        self.release_count = 0
        self._listeners = []

    def acquire(self, tag):
        self.acquire_count += 1

    def release(self, tag):
        self.release_count += 1

    def add_session_listener(self, listener):
        self._listeners.append(listener)

        def unsubscribe():
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def call_started(self, at):
        self.call_state = DEVICE_OFFHOOK
        for listener in list(self._listeners):
            listener(Started(at))

    def call_ended(self, duration_ms):
        self.call_state = DEVICE_IDLE
        for listener in list(self._listeners):
            listener(Ended(duration_ms))


class FakeStore:
    """Thread-safe: the race tests drive it from real threads. Counts every
    write ATTEMPT, including ones the status guard rejects — the race
    regression tests assert the losing caller issues no attempt at all."""

    def __init__(self):
        self.rows = {}
        self._lock = threading.Lock()
        self.transition_attempts = 0
        self.delete_pending_attempts = 0

    def insert_pending(self, transaction):
        with self._lock:
            self.rows[transaction.transactionId] = transaction

    def transition_status(self, transaction_id, expected_status, new_status):
        with self._lock:
            self.transition_attempts += 1
            row = self.rows.get(transaction_id)
            if row is None or row.status != expected_status:
                return 0
            self.rows[transaction_id] = Transaction(
                **{**row.__dict__, "status": new_status}
            )
            return 1

    def confirm_transaction(self, transaction_id, status, parsed, verified_at):
        with self._lock:
            # Mirrors the DAO's status guard: a confirmation only lands on a
            # row still awaiting one, never on a cancelled or settled row.
            row = self.rows.get(transaction_id)
            if row is None or row.status != PENDING:
                return 0
            self.rows[transaction_id] = Transaction(
                **{
                    **row.__dict__,
                    "status": status,
                    "bankRef": parsed.transaction_id,
                    "bankName": parsed.bank_name,
                    "smsExcerpt": parsed.sms_excerpt,
                    # Mirrors the DAO: sparser SMS data never erases known
                    # values; amount fills only when the row started without
                    # one (QR flow).
                    "upiId": parsed.upi_id or row.upiId,
                    "recipientName": parsed.recipient_name or row.recipientName,
                    "amount": row.amount or parsed.amount,
                    "verifiedAt": verified_at,
                }
            )
            return 1

    def delete_stale_pending(self, now):
        with self._lock:
            stale = [
                k
                for k, row in self.rows.items()
                if row.status == PENDING and row.deadlineAt is not None and row.deadlineAt < now
            ]
            for k in stale:
                del self.rows[k]
            return len(stale)

    def delete_pending(self, transaction_id):
        with self._lock:
            self.delete_pending_attempts += 1
            row = self.rows.get(transaction_id)
            if row is not None and row.status == PENDING:
                del self.rows[transaction_id]
                return 1
            return 0


class ManualWatchdog:
    """Deterministic verification deadline: fire() runs the callback unless
    the watchdog was cancelled (mirroring the coroutine delay job)."""

    def __init__(self):
        self.callback = None
        self.delay_ms = None
        self.cancelled = False

    def factory(self, delay_ms, callback):
        self.delay_ms = delay_ms
        self.callback = callback
        return self

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled and self.callback is not None:
            self.callback()


class FakeClock:
    def __init__(self, now=0):
        self.now = now

    def __call__(self):
        return self.now


def new_manager(store=None, source=None, clock=None):
    store = store or FakeStore()
    source = source or FakeCallStateSource()
    clock = clock or FakeClock()
    watchdog = ManualWatchdog()
    manager = PaymentSessionManager(
        store=store,
        coordinator=source,
        clock=clock,
        watchdog_factory=watchdog.factory,
    )
    return manager, store, source, watchdog, clock


def bank_sms(status="SUCCESS", amount="100", transaction_type="DEBIT"):
    return SimpleTransaction(
        transaction_id="HDFC123456",
        amount=amount,
        status=status,
        bank_name="HDFC Bank",
        sms_excerpt=f"₹{amount} debited — HDFC Bank · Ref HDFC123456",
        timestamp=0,
        transaction_type=transaction_type,
    )


def test_begin_records_a_pending_row_before_any_call_activity():
    manager, store, source, _, _ = new_manager()

    txn_id = manager.begin("9876543210", "100")

    assert txn_id
    assert isinstance(manager.payment_state, ps.Initiating)
    row = store.rows.get(txn_id)
    assert row is not None, "PENDING row must exist before dialing"
    assert row.status == PENDING
    assert row.phoneNumber == "9876543210"
    assert row.deadlineAt is not None, "deadline must be persisted"
    assert source.acquire_count == 1


def test_second_begin_supersedes_the_session_still_in_flight():
    manager, store, _, _, _ = new_manager()

    first = manager.begin("9876543210", "100")
    assert store.rows[first].status == PENDING

    second = manager.begin("9123456780", "200")

    assert first != second, "the new payment must get its own id"
    assert isinstance(manager.payment_state, ps.Initiating)
    assert store.rows[second].phoneNumber == "9123456780"
    assert store.rows[second].amount == "200"
    # The superseded attempt was never confirmed, so under the
    # "no confirmation, no record" rule it leaves no trace.
    assert first not in store.rows, "superseded PENDING row must be discarded"


def test_superseding_does_not_erase_an_already_confirmed_row():
    manager, store, source, _, _ = new_manager()
    first = manager.begin("9876543210", "500")
    source.call_started(at=0)
    manager.on_sms_confirmed(bank_sms(amount="500"))
    assert store.rows[first].status == SUCCESS

    manager.begin("9123456780", "200")

    assert first in store.rows, "a confirmed row must survive a later payment"
    assert store.rows[first].status == SUCCESS


def test_call_start_moves_session_to_in_progress():
    manager, _, source, _, _ = new_manager()
    manager.begin("9876543210", "100")

    source.call_started(at=0)

    assert isinstance(manager.payment_state, ps.InProgress)


def test_confirming_sms_during_call_yields_success_row_with_bank_reference():
    manager, store, source, _, _ = new_manager()
    txn_id = manager.begin("9876543210", "100")
    source.call_started(at=0)

    claimed = manager.on_sms_confirmed(bank_sms())

    assert claimed == txn_id
    assert isinstance(manager.payment_state, ps.Success)
    row = store.rows[txn_id]
    assert row.status == SUCCESS
    assert row.bankRef == "HDFC123456"
    assert row.bankName == "HDFC Bank"
    assert row.verifiedAt is not None


def test_short_call_without_sms_is_cancelled_never_success():
    manager, store, source, _, _ = new_manager()
    txn_id = manager.begin("9876543210", "100")
    source.call_started(at=0)

    source.call_ended(duration_ms=2_000)

    assert isinstance(manager.payment_state, ps.Cancelled)
    assert store.rows[txn_id].status == CANCELLED


def test_normal_call_end_without_sms_waits_for_verification_then_sms_confirms():
    manager, store, source, _, _ = new_manager()
    txn_id = manager.begin("9876543210", "100")
    source.call_started(at=0)
    source.call_ended(duration_ms=40_000)

    assert isinstance(
        manager.payment_state, ps.WaitingForVerification
    ), "call duration must never be treated as success"
    assert store.rows[txn_id].status == PENDING

    claimed = manager.on_sms_confirmed(bank_sms())

    assert claimed == txn_id
    assert isinstance(manager.payment_state, ps.Success)
    assert store.rows[txn_id].status == SUCCESS


def test_no_sms_before_deadline_discards_the_row_and_emits_timeout():
    # No confirming SMS means there is no payment to report: the row is
    # discarded rather than left behind as an outcome the user can't act on.
    # The Timeout state is still emitted so observers wind themselves down.
    manager, store, source, watchdog, _ = new_manager()
    txn_id = manager.begin("9876543210", "100")
    source.call_started(at=0)
    source.call_ended(duration_ms=40_000)

    watchdog.fire()

    assert isinstance(manager.payment_state, ps.Timeout)
    assert txn_id not in store.rows, "An unconfirmed payment must leave no row behind"


def test_qr_session_records_vpa_and_source_and_the_confirming_sms_fills_the_amount():
    # The QR flow starts before the user has typed an amount into the USSD
    # menu, and pays a VPA rather than a phone number. The PENDING row must
    # still capture what IS known, and the bank's confirmation must fill the
    # missing amount — QR payments used to bypass the session entirely and
    # leave no trace when no SMS arrived.
    manager, store, source, _, _ = new_manager()

    txn_id = manager.begin(
        phone_number="",
        amount="",
        upi_id="kirana@okhdfcbank",
        source="QR",
    )

    pending = store.rows[txn_id]
    assert pending.status == PENDING
    assert pending.upiId == "kirana@okhdfcbank"
    assert pending.source == "QR"

    source.call_started(at=0)
    manager.on_sms_confirmed(bank_sms(amount="750"))

    confirmed = store.rows[txn_id]
    assert confirmed.status == SUCCESS
    assert confirmed.amount == "750", "SMS amount must fill the empty QR amount"
    assert confirmed.upiId == "kirana@okhdfcbank", "VPA must survive a sparser SMS"


def test_failed_bank_sms_yields_failed_row_and_failed_state():
    manager, store, source, _, _ = new_manager()
    txn_id = manager.begin("9876543210", "100")
    source.call_started(at=0)

    manager.on_sms_confirmed(bank_sms(status=FAILED))

    assert isinstance(manager.payment_state, ps.Failed)
    assert store.rows[txn_id].status == FAILED


def test_sms_with_no_active_session_is_not_claimed():
    manager, _, _, _, _ = new_manager()

    assert manager.on_sms_confirmed(bank_sms()) is None


def test_truly_concurrent_confirmations_exactly_one_claims_the_session():
    # The check-and-claim inside on_sms_confirmed is a single atomic step.
    # Two near-simultaneous SMS (both pipelines, or a debug injection racing
    # a real message) must not both observe InProgress and both write a
    # terminal outcome, last-writer-wins.
    store = FakeStore()
    source = FakeCallStateSource()
    watchdog = ManualWatchdog()
    manager = PaymentSessionManager(
        store=store, coordinator=source, watchdog_factory=watchdog.factory
    )
    txn_id = manager.begin("9876543210", "100")
    source.call_started(at=0)
    assert isinstance(manager.payment_state, ps.InProgress)

    results = []
    failures = []
    start_gate = threading.Event()

    def race(sms):
        try:
            start_gate.wait(5)
            results.append(manager.on_sms_confirmed(sms))
        except Exception as e:  # pragma: no cover - failure path
            failures.append(e)

    t1 = threading.Thread(target=race, args=(bank_sms(status=SUCCESS),))
    t2 = threading.Thread(target=race, args=(bank_sms(status=FAILED),))
    t1.start()
    t2.start()
    start_gate.set()
    t1.join(5)
    t2.join(5)

    assert not failures, f"no exception during the race: {failures[:1]}"
    claimed = [r for r in results if r is not None]
    assert claimed == [txn_id], "exactly one confirmation may claim the session"

    terminal = manager.payment_state
    expected = FAILED if isinstance(terminal, ps.Failed) else SUCCESS
    assert isinstance(terminal, (ps.Success, ps.Failed))
    assert store.rows[txn_id].status == expected


def test_incoming_credit_sms_never_confirms_an_outgoing_debit_session():
    manager, store, source, _, _ = new_manager()
    txn_id = manager.begin("9876543210", "100")
    source.call_started(at=0)

    claimed = manager.on_sms_confirmed(bank_sms(transaction_type="CREDIT"))

    assert claimed is None, "credit SMS must not be claimed by a debit session"
    assert isinstance(
        manager.payment_state, ps.InProgress
    ), "session must stay live for the real confirmation"
    assert store.rows[txn_id].status == PENDING


def test_needs_review_confirmation_yields_needs_review_row_and_state():
    manager, store, source, _, _ = new_manager()
    txn_id = manager.begin("9876543210", "100")
    source.call_started(at=0)

    claimed = manager.on_sms_confirmed(bank_sms(status=NEEDS_REVIEW, amount="499"))

    assert claimed == txn_id
    assert isinstance(manager.payment_state, ps.NeedsReview)
    assert store.rows[txn_id].status == NEEDS_REVIEW


def test_second_sms_confirmed_after_terminal_state_is_not_claimed():
    manager, store, source, _, _ = new_manager()
    txn_id = manager.begin("9876543210", "100")
    source.call_started(at=0)

    first = manager.on_sms_confirmed(bank_sms())
    second = manager.on_sms_confirmed(bank_sms())

    assert first == txn_id
    assert second is None, "terminal session must not claim a second SMS"
    assert store.rows[txn_id].status == SUCCESS


def test_dial_failure_cancels_the_session():
    manager, store, source, _, _ = new_manager()
    txn_id = manager.begin("9876543210", "100")

    manager.on_dial_failed("Could not start the payment call")

    assert isinstance(manager.payment_state, ps.Cancelled)
    assert store.rows[txn_id].status == CANCELLED
    assert source.release_count == 1, "coordinator must be released on terminal state"


def test_user_cancellation_from_the_overlay_ends_the_session_as_cancelled():
    manager, store, source, _, _ = new_manager()
    txn_id = manager.begin("9876543210", "100")
    source.call_started(at=0)

    manager.on_user_cancelled()

    assert isinstance(manager.payment_state, ps.Cancelled)
    assert store.rows[txn_id].status == CANCELLED
    assert source.release_count == 1, "coordinator must be released on terminal state"


def test_on_user_cancelled_is_a_safe_no_op_with_no_active_session():
    manager, _, _, _, _ = new_manager()

    # A stray overlay callback (or a defensive retry after a caught
    # exception) with nothing in flight — must not throw.
    manager.on_user_cancelled()

    assert manager.payment_state == ps.IDLE


def test_on_user_cancelled_called_twice_does_not_double_transition_or_crash():
    manager, store, source, _, _ = new_manager()
    txn_id = manager.begin("9876543210", "100")
    source.call_started(at=0)

    # Mirrors CallOverlayService.handleTerminateCall calling this again from
    # its catch block after cleanup below it throws.
    manager.on_user_cancelled()
    manager.on_user_cancelled()

    assert isinstance(manager.payment_state, ps.Cancelled)
    assert store.rows[txn_id].status == CANCELLED
    assert source.release_count == 1, "second call must not release the coordinator again"


def test_call_never_starting_during_initiating_ends_the_session_as_cancelled():
    manager, store, source, _, _ = new_manager()
    txn_id = manager.begin("9876543210", "100")

    assert isinstance(
        manager.payment_state, ps.Initiating
    ), "precondition: session must still be Initiating (no OFFHOOK yet)"

    manager.on_call_never_started()

    assert isinstance(manager.payment_state, ps.Cancelled)
    assert store.rows[txn_id].status == CANCELLED
    assert source.release_count == 1, "coordinator must be released on terminal state"


def test_on_call_never_started_is_a_no_op_once_the_call_has_actually_started():
    manager, store, source, _, _ = new_manager()
    txn_id = manager.begin("9876543210", "100")
    source.call_started(at=0)
    assert isinstance(manager.payment_state, ps.InProgress)

    # The overlay's 40s watchdog firing late, after OFFHOOK already arrived,
    # must not cancel a call that is genuinely in progress.
    manager.on_call_never_started()

    assert isinstance(manager.payment_state, ps.InProgress)
    assert store.rows[txn_id].status == PENDING


def test_acknowledge_returns_terminal_session_to_idle_and_allows_a_new_begin():
    manager, _, source, _, _ = new_manager()
    manager.begin("9876543210", "100")
    manager.on_dial_failed("failed")

    manager.acknowledge_result()
    assert manager.payment_state == ps.IDLE

    nxt = manager.begin("9123456780", "50")
    assert nxt is not None, "new session must be possible after acknowledge"
    assert source.acquire_count == 2


def test_stale_pending_rows_are_discarded_on_next_begin():
    store = FakeStore()
    store.rows["stale"] = Transaction(
        transactionId="stale",
        amount="75",
        status=PENDING,
        bankName="",
        smsExcerpt="",
        timestamp=0,
        deadlineAt=1,
    )
    clock = FakeClock(now=10_000)
    manager, store, _, _, _ = new_manager(store=store, clock=clock)

    manager.begin("9876543210", "100")

    assert "stale" not in store.rows, "Stale unconfirmed rows must be removed"


def test_a_confirming_sms_cannot_resurrect_a_cancelled_row():
    # A cancelled payment must stay cancelled. The user may well re-pay the
    # same amount through another app minutes later; that bank SMS must not
    # be able to rewrite this row into a success.
    manager, store, source, _, _ = new_manager()
    txn_id = manager.begin("9876543210", "500")
    source.call_started(at=0)
    manager.on_user_cancelled()
    assert store.rows[txn_id].status == CANCELLED

    claimed = manager.on_sms_confirmed(
        SimpleTransaction(
            transaction_id="BANKREF999",
            amount="500",
            status=SUCCESS,
            bank_name="HDFC Bank",
            sms_excerpt="₹500 debited — HDFC Bank",
            timestamp=0,
            transaction_type="DEBIT",
        )
    )

    assert claimed is None, "A cancelled session must not claim a later SMS"
    assert store.rows[txn_id].status == CANCELLED


# ---- Claim-before-write invariant -----------------------------------------
# Exactly one caller may reach a terminal state, and ONLY that caller may
# write. finish_session/on_verification_deadline used to queue their row
# write before claiming, then re-check — so a cancel landing at the same
# instant as the bank's SMS could show "Payment successful" while the
# already-queued PENDING->CANCELLED write still ran, leaving history
# contradicting the screen the user was looking at.


def test_cancel_after_a_confirmation_claims_nothing_and_writes_nothing():
    manager, store, source, _, _ = new_manager()
    txn_id = manager.begin("9876543210", "500")
    source.call_started(at=0)

    assert manager.on_sms_confirmed(bank_sms(amount="500")) == txn_id
    attempts_after_confirm = store.transition_attempts

    manager.on_user_cancelled()

    assert isinstance(manager.payment_state, ps.Success), "SMS must own the outcome"
    assert store.rows[txn_id].status == SUCCESS
    assert (
        store.transition_attempts == attempts_after_confirm
    ), "The losing caller must not issue a write at all"


def test_deadline_after_a_confirmation_deletes_nothing():
    manager, store, source, watchdog, _ = new_manager()
    txn_id = manager.begin("9876543210", "500")
    source.call_started(at=0)

    assert manager.on_sms_confirmed(bank_sms(amount="500")) == txn_id

    # The verification watchdog was cancelled by the confirmation; firing it
    # now must not delete the row the confirmation just landed on.
    watchdog.fire()

    assert store.delete_pending_attempts == 0
    assert txn_id in store.rows, "The confirmed row must survive the deadline"
    assert store.rows[txn_id].status == SUCCESS


def test_concurrent_cancel_and_confirmation_never_disagree():
    # The real interleaving, on real threads: a user tapping cancel at the
    # same instant the bank's SMS lands. Whoever wins, the stored row and
    # the state the UI renders must agree — that is the whole invariant.
    for iteration in range(100):
        store = FakeStore()
        source = FakeCallStateSource()
        watchdog = ManualWatchdog()
        manager = PaymentSessionManager(
            store=store, coordinator=source, watchdog_factory=watchdog.factory
        )
        txn_id = manager.begin("9876543210", "500")
        # The PENDING row exists synchronously in this port — no insert race.

        barrier = threading.Barrier(2)

        def sms_racer():
            barrier.wait()
            manager.on_sms_confirmed(bank_sms(amount="500"))

        def cancel_racer():
            barrier.wait()
            manager.on_user_cancelled()

        sms_thread = threading.Thread(target=sms_racer)
        cancel_thread = threading.Thread(target=cancel_racer)
        sms_thread.start()
        cancel_thread.start()
        sms_thread.join(5)
        cancel_thread.join(5)

        state = manager.payment_state
        if isinstance(state, ps.Success):
            expected = SUCCESS
        elif isinstance(state, ps.Cancelled):
            expected = CANCELLED
        else:
            raise AssertionError(f"iteration {iteration}: unexpected terminal state {state!r}")
        assert store.rows[txn_id].status == expected, (
            f"iteration {iteration}: stored row must match the reported outcome"
        )
        assert store.transition_attempts == (1 if expected == CANCELLED else 0), (
            f"iteration {iteration}: only the winning caller may write"
        )
