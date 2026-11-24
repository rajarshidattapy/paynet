# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/test/java/com/paynet/app/data/TransactionMappingTest.kt and
# app/src/test/java/com/paynet/app/ui/activities/TransactionPresentationTest.kt

import calendar

from paynet import status as txn_status
from paynet.db.models import PaymentStatus, Transaction
from paynet.ui.presentation import historical_date_label, matches_search


def _row(status: str) -> Transaction:
    return Transaction(
        transactionId="t1",
        amount="100",
        status=status,
        bankName="HDFC Bank",
        smsExcerpt="",
        timestamp=0,
        transactionType="DEBIT",
        phoneNumber="9876543210",
    )


def test_each_canonical_status_maps_to_its_own_payment_status():
    assert _row(txn_status.SUCCESS).to_payment_details().status is PaymentStatus.COMPLETED
    assert _row(txn_status.FAILED).to_payment_details().status is PaymentStatus.FAILED
    assert _row(txn_status.CANCELLED).to_payment_details().status is PaymentStatus.CANCELLED
    assert _row(txn_status.PENDING).to_payment_details().status is PaymentStatus.PENDING
    assert _row(txn_status.UNVERIFIED).to_payment_details().status is PaymentStatus.UNVERIFIED
    assert _row(txn_status.NEEDS_REVIEW).to_payment_details().status is PaymentStatus.NEEDS_REVIEW


def test_unverified_and_needs_review_are_not_collapsed_into_pending():
    assert _row(txn_status.UNVERIFIED).to_payment_details().status is PaymentStatus.UNVERIFIED
    assert _row(txn_status.NEEDS_REVIEW).to_payment_details().status is PaymentStatus.NEEDS_REVIEW


def test_unknown_status_falls_back_to_pending():
    assert _row("WHATEVER").to_payment_details().status is PaymentStatus.PENDING


ROW = Transaction(
    "presentation-test", "", "USER_CONFIRMED", "Example bank", "",
    recipientName=" SAMPLE MERCHANT ", phoneNumber="9876543210",
    upiId="merchant@bank", bankRef="REF-12345",
)


def _replace(transaction, **changes):
    import dataclasses

    return dataclasses.replace(transaction, **changes)


def test_recipient_fallback_is_consistent_and_does_not_change_raw_data():
    assert ROW.recipient_label == "Sample Merchant"
    assert ROW.to_payment_details().recipient_label == ROW.recipient_label
    assert ROW.recipientName == " SAMPLE MERCHANT "
    assert _replace(ROW, recipientName=" ").recipient_label == "9876543210"
    qr = _replace(ROW, recipientName=None, phoneNumber=" ")
    assert qr.recipient_label == "merchant@bank"
    assert qr.to_payment_details().recipient_label == qr.recipient_label
    assert _replace(qr, upiId=None).recipient_label is None


def test_unrecorded_amount_remains_different_from_recorded_zero():
    assert not ROW.to_payment_details().amountRecorded
    assert not _replace(ROW, amount=" ").to_payment_details().amountRecorded
    assert _replace(ROW, amount="0").to_payment_details().amountRecorded
    assert _replace(ROW, amount="1.25").to_payment_details().amountRecorded


def test_search_finds_identifiers_and_trims_pasted_whitespace():
    assert matches_search(ROW, "  MERCHANT@BANK  ")
    assert matches_search(ROW, "ref-123")
    assert matches_search(ROW, "987654")
    assert matches_search(ROW, "sample")
    assert matches_search(ROW, " ")
    assert not matches_search(ROW, "someone-else@bank")


def _date_ms(year: int, month: int, day: int) -> int:
    # month is 1-based here; noon local time
    return calendar.timegm((year, month, day, 12, 0, 0, 0, 0, 0, 0)) * 1000


def test_older_dates_keep_their_year():
    now = _date_ms(2026, 11, 3)
    assert historical_date_label(_date_ms(2026, 10, 15), now) == "15 Oct"
    assert historical_date_label(_date_ms(2025, 10, 15), now) == "15 Oct 2025"
    assert historical_date_label(_date_ms(2024, 10, 15), now) != historical_date_label(
        _date_ms(2025, 10, 15), now
    )
