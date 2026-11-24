# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Behavioral tests for the sqlite port of TransactionDao/AppDatabase. The
# lifecycle guards (confirm-only-PENDING, stale-pending discard, COALESCE
# preservation) are the payment-critical semantics being locked here.

import pytest

from paynet import status as txn_status
from paynet.db.database import Database
from paynet.db.models import Transaction
from paynet.repository import TransactionRepository
from paynet.sms.parser import SimpleTransaction


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    yield database
    database.close()


def _txn(transaction_id="t1", status="SUCCESS", timestamp=1000, amount="100",
           bankName="HDFC Bank", **kwargs):
    return Transaction(
        transactionId=transaction_id,
        amount=amount,
        status=status,
        bankName=bankName,
        smsExcerpt="",
        timestamp=timestamp,
        transactionType="DEBIT",
        **kwargs,
    )


def test_insert_and_read_back_round_trip(db):
    db.insert_transaction(_txn(upiId="a@b", recipientName="Kirana Store"))
    row = db.get_transaction_by_id("t1")
    assert row is not None
    assert row.upiId == "a@b"
    assert row.recipientName == "Kirana Store"
    assert row.transactionType == "DEBIT"


def test_insert_replaces_on_conflict(db):
    db.insert_transaction(_txn(status="PENDING"))
    db.insert_transaction(_txn(status="SUCCESS"))
    assert db.get_transaction_count() == 1
    assert db.get_transaction_by_id("t1").status == "SUCCESS"


def test_ordering_is_newest_first_and_limit_applies(db):
    for index in range(15):
        db.insert_transaction(_txn(f"t{index}", timestamp=index))
    recent = db.get_recent_transactions(10)
    assert len(recent) == 10
    assert recent[0].transactionId == "t14"
    assert [t.timestamp for t in recent] == sorted(
        (t.timestamp for t in recent), reverse=True
    )


def test_recent_confirmed_excludes_pending(db):
    db.insert_transaction(_txn("p1", status="PENDING", timestamp=2000))
    db.insert_transaction(_txn("s1", status="SUCCESS", timestamp=1000))
    recent = db.get_recent_confirmed_transactions()
    assert [t.transactionId for t in recent] == ["s1"]


def test_status_bank_and_search_queries(db):
    db.insert_transaction(_txn("a", status="FAILED", bankName="Axis Bank",
                               recipientName="Cafe Day", phoneNumber="9000000001"))
    db.insert_transaction(_txn("b", status="SUCCESS", bankName="HDFC Bank",
                               recipientName="Metro", phoneNumber="9000000002"))
    assert [t.transactionId for t in db.get_transactions_by_status("FAILED")] == ["a"]
    assert [t.transactionId for t in db.get_transactions_by_bank("HDFC Bank")] == ["b"]
    assert [t.transactionId for t in db.search_transactions("%cafe%")] == ["a"]
    assert [t.transactionId for t in db.search_transactions("%9000000002%")] == ["b"]


def test_total_amount_sums_completed_only(db):
    db.insert_transaction(_txn("a", status="SUCCESS", amount="100.50"))
    db.insert_transaction(_txn("b", status="COMPLETED", amount="49.50"))
    db.insert_transaction(_txn("c", status="FAILED", amount="999"))
    assert db.get_total_amount() == pytest.approx(150.0)


def test_date_range_query(db):
    db.insert_transaction(_txn("in", timestamp=1500))
    db.insert_transaction(_txn("out", timestamp=500))
    rows = db.get_transactions_by_date_range(1000, 2000)
    assert [t.transactionId for t in rows] == ["in"]


def test_transition_status_is_guarded_by_expected_status(db):
    db.insert_transaction(_txn(status="PENDING"))
    # Wrong expected status -> no change
    assert db.transition_status("t1", "SUCCESS", "CANCELLED") == 0
    assert db.get_transaction_by_id("t1").status == "PENDING"
    # Right expected status -> moves
    assert db.transition_status("t1", "PENDING", "CANCELLED") == 1
    assert db.get_transaction_by_id("t1").status == "CANCELLED"


def test_confirm_transaction_fills_details_and_marks_success(db):
    db.insert_transaction(_txn(status="PENDING", amount="", upiId="session@upi"))
    parsed = SimpleTransaction(
        transaction_id="512233440091_42",
        amount="500.00",
        status=txn_status.SUCCESS,
        bank_name="HDFC Bank",
        sms_excerpt="₹500.00 debited — HDFC Bank",
        recipient_name="Kirana Store",
    )
    changed = db.confirm_transaction(
        transaction_id="t1",
        status=txn_status.SUCCESS,
        bank_ref=parsed.transaction_id,
        bank_name=parsed.bank_name,
        sms_excerpt=parsed.sms_excerpt,
        upi_id=None,
        recipient_name=parsed.recipient_name,
        amount=parsed.amount,
        verified_at=4242,
    )
    assert changed == 1
    row = db.get_transaction_by_id("t1")
    assert row.status == "SUCCESS"
    assert row.amount == "500.00"  # filled because the row started blank
    assert row.upiId == "session@upi"  # COALESCE: session value not erased
    assert row.recipientName == "Kirana Store"
    assert row.bankRef == "512233440091_42"
    assert row.verifiedAt == 4242


def test_confirm_transaction_never_rewrites_a_cancelled_row(db):
    db.insert_transaction(_txn(status="CANCELLED", amount="500"))
    parsed = SimpleTransaction(
        transaction_id="ref_1",
        amount="500.00",
        status=txn_status.SUCCESS,
        bank_name="HDFC Bank",
        sms_excerpt="x",
    )
    changed = db.confirm_transaction(
        transaction_id="t1",
        status=txn_status.SUCCESS,
        bank_ref=parsed.transaction_id,
        bank_name=parsed.bank_name,
        sms_excerpt=parsed.sms_excerpt,
        upi_id=None,
        recipient_name=None,
        amount=parsed.amount,
        verified_at=1,
    )
    assert changed == 0
    assert db.get_transaction_by_id("t1").status == "CANCELLED"


def test_delete_stale_pending_only_removes_expired_pending(db):
    db.insert_transaction(_txn("expired", status="PENDING", deadlineAt=999))
    db.insert_transaction(_txn("fresh", status="PENDING", deadlineAt=2000))
    db.insert_transaction(_txn("nodeadline", status="PENDING", deadlineAt=None))
    db.insert_transaction(_txn("done", status="SUCCESS", deadlineAt=999))
    assert db.delete_stale_pending(now=1000) == 1
    assert db.get_transaction_by_id("expired") is None
    assert db.get_transaction_by_id("fresh") is not None
    assert db.get_transaction_by_id("nodeadline") is not None
    assert db.get_transaction_by_id("done") is not None


def test_delete_pending_only_deletes_pending_rows(db):
    db.insert_transaction(_txn("p", status="PENDING"))
    db.insert_transaction(_txn("s", status="SUCCESS"))
    assert db.delete_pending("s") == 0
    assert db.delete_pending("p") == 1
    assert db.get_transaction_by_id("s") is not None


def test_repository_save_and_recent_payment_details(tmp_path):
    repo = TransactionRepository(Database(str(tmp_path / "repo.db")))
    parsed = SimpleTransaction(
        transaction_id="ref_9",
        amount="250.00",
        status=txn_status.SUCCESS,
        bank_name="ICICI Bank",
        sms_excerpt="₹250.00 debited — ICICI Bank",
        recipient_name="RAHUL SHARMA",
    )
    repo.save_transaction(parsed)
    row = repo.get_transaction_by_id("ref_9")
    assert row is not None
    assert row.source == txn_status.SOURCE_SMS
    assert row.bankRef == "ref_9"

    details = repo.get_recent_payment_details()
    assert len(details) == 1
    assert details[0].recipient_label == "Rahul Sharma"
    assert details[0].amount == 250.0
