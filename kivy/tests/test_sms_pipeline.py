# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/test/java/com/paynet/app/receivers/SmsIngestionPipelineTest.kt
# plus coverage for the TransactionDetector window/dedup semantics from
# app/src/main/java/com/paynet/app/helpers/TransactionDetector.kt

"""The ownership decision for an incoming confirmation: live session first,
then reattach-to-orphaned-row (process died mid-payment), else standalone
insert. Without the reattach a killed process turned one payment into two
rows — a fresh SUCCESS plus the original expiring to UNVERIFIED.
"""

import threading

from paynet.db.settings import PrefsStore
from paynet.sms.detector import (
    OPERATION_WINDOW_MILLIS,
    SMS_CLAIM_WINDOW_MILLIS,
    TransactionDetector,
)
from paynet.sms.parser import SimpleTransaction
from paynet.sms.pipeline import is_unrelated_incoming_credit, resolve_owner_txn_id


def parsed(type="DEBIT"):
    return SimpleTransaction(
        transaction_id="BANKREF123",
        amount="500",
        status="SUCCESS",
        bank_name="HDFC Bank",
        sms_excerpt="₹500 debited — HDFC Bank",
        timestamp=0,
        transaction_type=type,
    )


# ---- SmsIngestionPipelineTest (1:1) -----------------------------------------


def test_live_session_always_owns_the_confirmation():
    adopted = []

    def adopt(txn_id):
        adopted.append(txn_id)
        return 1

    owner = resolve_owner_txn_id(
        session_txn_id="session-1", window_txn_id="window-1", parsed=parsed(), adopt=adopt
    )

    assert owner == "session-1"
    assert adopted == [], "no adoption when a live session claimed it"


def test_orphaned_row_is_adopted_after_process_death():
    adopted = []

    def adopt(txn_id):
        adopted.append(txn_id)
        return 1

    owner = resolve_owner_txn_id(
        session_txn_id=None, window_txn_id="window-1", parsed=parsed(), adopt=adopt
    )

    assert owner == "window-1"
    assert adopted == ["window-1"]


def test_missing_row_falls_back_to_standalone_insert():
    # Row no longer exists (e.g. history cleared) -> adopt updates 0 rows.
    owner = resolve_owner_txn_id(
        session_txn_id=None, window_txn_id="window-1", parsed=parsed(), adopt=lambda _: 0
    )

    assert owner is None


def test_a_credit_never_adopts_the_outgoing_debit_row():
    adopt_calls = []

    def adopt(txn_id):
        adopt_calls.append(txn_id)
        return 1

    owner = resolve_owner_txn_id(
        session_txn_id=None, window_txn_id="window-1", parsed=parsed(type="CREDIT"), adopt=adopt
    )

    assert owner is None
    assert adopt_calls == []


def test_no_window_txnid_means_standalone_insert():
    owner = resolve_owner_txn_id(
        session_txn_id=None, window_txn_id=None, parsed=parsed(), adopt=lambda _: 1
    )

    assert owner is None


def test_adoption_failure_is_contained_and_falls_back_to_standalone_insert():
    def adopt(_):
        raise RuntimeError("db unavailable")

    owner = resolve_owner_txn_id(
        session_txn_id=None, window_txn_id="window-1", parsed=parsed(), adopt=adopt
    )

    assert owner is None


def test_unclaimed_incoming_credit_in_the_window_is_ignored():
    # An unrelated incoming credit (salary, refund, someone paying you) can
    # land inside the operation window while an outgoing payment is still
    # pending. It never confirms our DEBIT, so it must not surface a result
    # screen, post a notification, or be saved as a payment.
    assert is_unrelated_incoming_credit(record_txn_id=None, parsed=parsed(type="CREDIT")) is True


def test_an_outgoing_debit_is_never_treated_as_an_unrelated_credit():
    # Standalone QR-flow debit (no owning row) must still be surfaced/saved.
    assert is_unrelated_incoming_credit(record_txn_id=None, parsed=parsed(type="DEBIT")) is False


def test_a_claimed_confirmation_is_always_surfaced():
    # Defensive: if any future path ever lets a row own this ingestion,
    # surface it rather than silently dropping it.
    assert is_unrelated_incoming_credit(record_txn_id="session-1", parsed=parsed(type="DEBIT")) is False
    assert is_unrelated_incoming_credit(record_txn_id="session-1", parsed=parsed(type="CREDIT")) is False


# ---- TransactionDetector semantics ------------------------------------------


class FakeClock:
    def __init__(self, now=1_000_000):
        self.now = now

    def __call__(self):
        return self.now


def new_detector(tmp_path, clock=None):
    prefs = PrefsStore(str(tmp_path), "payment_operation")
    clock = clock or FakeClock()
    return TransactionDetector(prefs, clock=clock), clock


HDFC_SMS = (
    "Rs.500.00 debited from A/c **1234 to VPA kirana@okhdfcbank "
    "on 24-11-26. Ref No 612345678901. Not you? Call 18002586161 - HDFC Bank"
)


def test_window_inactive_means_no_processing(tmp_path):
    detector, _ = new_detector(tmp_path)

    assert detector.should_process_sms() is False
    assert detector.process_sms("VM-HDFCBK", HDFC_SMS) is None


def test_start_operation_opens_the_window_and_process_consumes_it(tmp_path):
    detector, _ = new_detector(tmp_path)
    detector.start_operation("PAYMENT", expected_amount="500", phone_number="9876543210", session_txn_id="txn-1")

    assert detector.should_process_sms() is True
    assert detector.get_operation_type() == "PAYMENT"
    assert detector.get_phone_number() == "9876543210"
    assert detector.get_session_txn_id() == "txn-1"

    transaction = detector.process_sms("VM-HDFCBK", HDFC_SMS)

    assert transaction is not None
    # A consuming match closes the window.
    assert detector.should_process_sms() is False
    assert detector.get_session_txn_id() is None


def test_window_expires_after_operation_window_and_stops_itself(tmp_path):
    detector, clock = new_detector(tmp_path)
    detector.start_operation("PAYMENT", expected_amount="500")
    assert detector.should_process_sms() is True

    clock.now += OPERATION_WINDOW_MILLIS + 1

    assert detector.should_process_sms() is False
    assert detector.get_operation_type() is None, "expired window must stop itself"


def test_a_credit_match_does_not_consume_the_window(tmp_path):
    # A stray credit must not consume the operation window the real
    # outgoing-debit confirmation may still need.
    credit_sms = (
        "Rs.5,000.00 credited to A/c **1234 on 24-11-26. "
        "Avl Bal Rs.25,000.00 - HDFC Bank"
    )
    detector, _ = new_detector(tmp_path)
    detector.start_operation("PAYMENT", expected_amount="500")

    transaction = detector.process_sms("VM-HDFCBK", credit_sms)

    assert transaction is not None
    assert transaction.transaction_type == "CREDIT"
    assert detector.should_process_sms() is True, "window must stay open for the genuine debit"


def test_try_claim_sms_dedupes_within_the_claim_window(tmp_path):
    detector, clock = new_detector(tmp_path)

    assert detector.try_claim_sms(HDFC_SMS) is True
    # A redelivered broadcast of the same message is rejected...
    assert detector.try_claim_sms(HDFC_SMS) is False
    # ...even cosmetically re-whitespaced (claim key is normalised).
    assert detector.try_claim_sms(HDFC_SMS.replace(" ", "  ")) is False

    clock.now += SMS_CLAIM_WINDOW_MILLIS
    assert detector.try_claim_sms(HDFC_SMS) is True, "claim expires after the window"


def test_concurrent_processing_only_one_pipeline_consumes_the_window(tmp_path):
    detector, _ = new_detector(tmp_path)
    detector.start_operation("PAYMENT", expected_amount="500")

    results = []
    barrier = threading.Barrier(2)

    def race():
        barrier.wait()
        results.append(detector.process_sms("VM-HDFCBK", HDFC_SMS))

    threads = [threading.Thread(target=race) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)

    consumed = [r for r in results if r is not None]
    assert len(consumed) == 1, "only the first pipeline inside consumes the active operation"
