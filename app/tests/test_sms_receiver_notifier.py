# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ports the guard logic of SimpleSMSReceiver and the notification mapping of
# PaymentResultNotifier (platform bindings are pyjnius work, see MIGRATION.md).

from paynet.db.settings import PrefsStore
from paynet.sms.detector import TransactionDetector
from paynet.sms.notifier import notification_text, notify_result, status_title
from paynet.sms.receiver import SimpleSMSReceiver

HDFC_SMS = (
    "Rs.500.00 debited from A/c **1234 to VPA kirana@okhdfcbank "
    "on 24-11-26. Ref No 612345678901. Not you? Call 18002586161 - HDFC Bank"
)


def new_receiver(tmp_path):
    detector = TransactionDetector(PrefsStore(str(tmp_path), "payment_operation"))
    ingested = []
    receiver = SimpleSMSReceiver(
        detector,
        ingest=lambda d, sender, body: ingested.append((sender, body)),
    )
    return receiver, detector, ingested


def test_receiver_ignores_sms_with_no_active_operation(tmp_path):
    receiver, _, ingested = new_receiver(tmp_path)

    assert receiver.handle_sms("VM-HDFCBK", HDFC_SMS) is False
    assert ingested == []


def test_receiver_ignores_blank_body_and_missing_sender(tmp_path):
    receiver, detector, ingested = new_receiver(tmp_path)
    detector.start_operation("PAYMENT", expected_amount="500")

    assert receiver.handle_sms("VM-HDFCBK", "   ") is False
    assert receiver.handle_sms(None, HDFC_SMS) is False
    assert ingested == []


def test_receiver_ingests_inside_the_window_only_once_per_message(tmp_path):
    receiver, detector, ingested = new_receiver(tmp_path)
    detector.start_operation("PAYMENT", expected_amount="500")

    assert receiver.handle_sms("VM-HDFCBK", HDFC_SMS) is True
    assert ingested == [("VM-HDFCBK", HDFC_SMS)]

    # A redelivered SMS_RECEIVED broadcast of the same message is claimed
    # already and never re-ingested.
    detector.start_operation("PAYMENT", expected_amount="500")
    assert receiver.handle_sms("VM-HDFCBK", HDFC_SMS) is False
    assert len(ingested) == 1


def test_notifier_title_mapping():
    assert status_title("SUCCESS") == "Payment Successful"
    assert status_title("FAILED") == "Payment Failed"
    assert status_title("NEEDS_REVIEW") == "Check This Payment"
    assert status_title("UNVERIFIED") == "No Confirmation Received"
    # Unknown statuses fall back to the success title, as in the Kotlin when-else.
    assert status_title("PENDING") == "Payment Successful"


def test_notifier_text_combines_amount_and_bank():
    assert notification_text("500", "HDFC Bank") == "₹500.00 — HDFC Bank"
    # One-character or empty parts are dropped (Kotlin: filter length > 1).
    assert notification_text("500", "") == "₹500.00"


def test_notify_result_posts_and_never_raises():
    posted = []
    notify_result(
        {"status": "SUCCESS", "amount": "500", "bank_name": "HDFC Bank", "transaction_id": "t1"},
        post=lambda nid, title, text: posted.append((nid, title, text)),
    )
    assert posted and posted[0][1] == "Payment Successful"
    assert posted[0][2] == "₹500.00 — HDFC Bank"

    def failing_post(nid, title, text):
        raise PermissionError("POST_NOTIFICATIONS denied")

    # Best-effort by design: a denied grant is a silent no-op, never a crash.
    notify_result({"status": "FAILED", "amount": "1", "bank_name": "b", "transaction_id": "t2"}, post=failing_post)
