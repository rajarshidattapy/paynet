# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/test/java/com/paynet/app/payment/QrWaitingStateTest.kt
# and app/src/test/java/com/paynet/app/payment/PaymentWindowObserverTest.kt
# (pure-mapping half; the observer itself is covered in test_payment_window.py)

from paynet.payment import state as ps
from paynet.payment.state import should_close_qr_waiting_screen
from paynet.payment.window import should_disarm_sms_window


# ---- QrWaitingStateTest ----------------------------------------------------


def test_deadline_closes_only_the_owning_screen():
    state = ps.Timeout(ps.TimeoutType.BANK_VERIFICATION, "", "500", "qr")
    assert should_close_qr_waiting_screen("qr", state)
    assert not should_close_qr_waiting_screen("other", state)
    assert not should_close_qr_waiting_screen(None, state)


def test_pending_confirmation_keeps_the_screen_open():
    state = ps.WaitingForVerification(0, "", "500", "qr")
    assert not should_close_qr_waiting_screen("qr", state)


def test_confirmed_result_closes_its_screen():
    state = ps.Success("qr", "", "500", "ref", 1)
    assert should_close_qr_waiting_screen("qr", state)
    assert not should_close_qr_waiting_screen("other", state)


# ---- PaymentWindowObserverTest (pure mapping) ------------------------------
# The SMS operation window must close when a payment is cancelled — left
# armed, it lets a later unrelated debit be adopted onto the cancelled row
# and reported as a success.


def test_a_cancelled_payment_closes_the_sms_window():
    assert should_disarm_sms_window(
        ps.Cancelled(
            phoneNumber="9876543210",
            amount="500",
            transactionId="txn-1",
            reason="Cancelled by user",
        )
    )


def test_a_timeout_leaves_the_window_open_for_its_remaining_grace():
    # The window deliberately outlives the verification deadline by 30s so a
    # slow-but-genuine confirmation still lands. Closing it here would
    # discard an SMS that did arrive.
    assert not should_disarm_sms_window(
        ps.Timeout(
            timeoutType=ps.TimeoutType.BANK_VERIFICATION,
            phoneNumber="9876543210",
            amount="500",
            transactionId="txn-1",
        )
    )


def test_settled_and_in_progress_states_never_close_the_window():
    # Success and failure consume the window in the ingestion path, and a
    # live payment obviously still needs it.
    states = [
        ps.IDLE,
        ps.Initiating(phoneNumber="9876543210", amount="500", transactionId="txn-1"),
        ps.InProgress(
            step="On the line with the UPI service",
            progress=0.5,
            phoneNumber="9876543210",
            amount="500",
            transactionId="txn-1",
        ),
        ps.Success(transactionId="txn-1", phoneNumber="9876543210", amount="500"),
        ps.Failed(
            error="declined",
            phoneNumber="9876543210",
            amount="500",
            transactionId="txn-1",
        ),
    ]
    for state in states:
        assert not should_disarm_sms_window(state), f"{state!r} must not close the SMS window"


# ---- PaymentState helpers ---------------------------------------------------


def test_terminal_and_in_progress_classification():
    assert not ps.IDLE.is_terminal()
    assert not ps.IDLE.is_in_progress()
    assert ps.Initiating("p", "1").is_in_progress()
    assert ps.InProgress("s", 0.4, "p", "1", "t").is_in_progress()
    assert ps.WaitingForVerification(0, "p", "1", "t").is_in_progress()
    for terminal in (
        ps.Success("t", "p", "1"),
        ps.Failed("e", "p", "1", "t"),
        ps.Cancelled("p", "1", "t"),
        ps.NeedsReview("t", "p", "1"),
    ):
        assert terminal.is_terminal()
        assert not terminal.is_in_progress()


def test_can_retry():
    assert ps.Failed("e", "p", "1", "t", canRetry=True).can_retry()
    assert not ps.Failed("e", "p", "1", "t", canRetry=False).can_retry()
    assert ps.Timeout(ps.TimeoutType.BANK_VERIFICATION, "p", "1", "t").can_retry()
    assert not ps.Success("t", "p", "1").can_retry()


def test_accessors_and_display():
    initiating = ps.Initiating("9876543210", "100", "txn-1")
    assert initiating.get_transaction_id() == "txn-1"
    assert initiating.get_phone_number() == "9876543210"
    assert initiating.get_amount() == "100"
    assert ps.IDLE.get_transaction_id() is None
    assert ps.IDLE.get_display_message() == "Ready to make payment"
    assert initiating.get_display_message() == "Initiating payment..."
    assert initiating.get_progress_percentage() == 0.1
    assert ps.WaitingForVerification(0, "p", "1", "t").get_progress_percentage() == 0.7
    assert ps.Success("t", "p", "1").get_progress_percentage() == 1.0
