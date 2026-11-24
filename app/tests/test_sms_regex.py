# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/test/java/com/paynet/app/helpers/SmsParsingRegexTest.kt

"""Smoke tests against paynet/sms/parser.py exercised directly. Broader
end-to-end coverage lives in test_sms_parser.py; this file documents the
individual regex-backed building blocks against real bank SMS samples."""

from paynet.sms import parser


def test_hdfc_debit_sms_bank_and_amount_extracted():
    sender = "VK-HDFCBK"
    body = "Rs.500.00 sent to KIRANA STORE from HDFC Bank A/c **1234 via UPI ref 123456789012 on 20-MAY-26"
    assert parser.detect_bank(sender, body) == "HDFC Bank"
    assert parser.extract_amount(body) == "500.00"


def test_icici_credit_sms_comma_separated_amount():
    sender = "AD-ICICIB"
    body = "INR 1,250.50 credited to your ICICI A/c on 20MAY26 from Rahul Sharma via UPI"
    assert parser.detect_bank(sender, body) == "ICICI Bank"
    assert parser.extract_amount(body) == "1250.50"


def test_sbi_ussd_style_sms_large_amount_with_commas():
    sender = "BP-SBIINB"
    body = "Rs 12,000 debited from your SBI A/c via UPI 9876543210 on 20/05/26. Ref: 123456789"
    assert parser.detect_bank(sender, body) == "State Bank of India"
    assert parser.extract_amount(body) == "12000"


def test_axis_bank_with_rupee_symbol():
    sender = "AX-AXISBK"
    body = "₹ 250.00 paid to merchant from Axis Bank A/c. UPI Ref: 99887766"
    assert parser.detect_bank(sender, body) == "Axis Bank"
    assert parser.extract_amount(body) == "250.00"


def test_kotak_sms_amount_before_rs_suffix():
    sender = "KT-KOTAKB"
    body = "100 Rs debited from Kotak A/c **5678. UPI Ref 11223344"
    assert parser.detect_bank(sender, body) == "Kotak Bank"
    assert parser.extract_amount(body) == "100"


def test_promotional_sms_not_detected_as_a_bank_transaction():
    sender = "JD-BIGSALE"
    body = "Win a Rs 50000 voucher today! Offer valid till month end."
    assert parser.detect_bank(sender, body) is None


def test_amount_extraction_handles_thousand_separators_and_decimals():
    assert parser.extract_amount("Rs 1,234,567 transferred") == "1234567"
    assert parser.extract_amount("INR 99.99 paid") == "99.99"
    assert parser.extract_amount("Rs 0.01 micro-debit") == "0.01"


def test_body_without_amount_returns_none():
    assert parser.extract_amount("Your OTP for HDFC is 123456. Do not share.") is None


def test_failure_sms_corpus_is_detected_as_failed():
    failures = [
        "Payment of Rs 500 failed. Ref 123456789012. -HDFC Bank",
        "Txn of INR 250.00 declined due to insufficient balance in A/c **1234",
        "Rs 120 reversed to your account **5678. Ref 998877 -SBI",
        "Your UPI payment of Rs.75 could not be processed. Please retry. -ICICI Bank",
        "UPI txn of Rs 300 was unsuccessful. A/c not debited. -AXIS",
        "Payment request of Rs 1,000 rejected by beneficiary bank. -KOTAK",
        "Your txn expired. Rs 50 payment was not completed. -PNB",
    ]
    for body in failures:
        assert parser.detects_failure(body), f"should detect failure: {body}"


def test_dlt_shaped_senders_match_the_generic_bank_fallback():
    body = "Rs 100 debited via UPI. Ref 123456789012"
    assert parser.detect_bank("VK-DBSBNK", body) == "Bank"  # alphanumeric DLT header
    assert parser.detect_bank("AD-BOIUPI-S", body) == "Bank"  # suffixed DLT header
    assert parser.detect_bank("561616", body) == "Bank"  # numeric shortcode
    assert parser.detect_bank("CTBBNK", body) == "Bank"  # bare 6-letter header


def test_mixed_case_6_char_senders_no_longer_match_the_fallback():
    promo_body = "Big sale! Get Rs 500 off today only."
    assert parser.detect_bank("Amazon", promo_body) is None
    assert parser.detect_bank("MyShop", promo_body) is None
    assert parser.detect_bank("Swiggy", promo_body) is None


def test_all_caps_6_letter_promo_sender_still_matches_documented_residual():
    # Deliberately kept: real bare DLT headers share this shape (HDFCBK,
    # SBIUPI). Downstream NEEDS_REVIEW/FAILED tiers are the safety net.
    assert parser.detect_bank("AMAZON", "Rs 500 off your next order") == "Bank"


def test_bank_keyword_in_sender_or_body_still_wins_over_the_fallback():
    assert parser.detect_bank("VM-HDFCBK", "Rs 100 debited") == "HDFC Bank"
    assert (
        parser.detect_bank("XY-123456", "Rs 100 debited from your SBI A/c")
        == "State Bank of India"
    )


def test_claim_key_converges_for_full_and_notification_truncated_bodies():
    full_body = (
        "Rs.500.00 sent to KIRANA STORE from HDFC Bank A/c **1234 via UPI ref 123456789012 "
        "on 20-MAY-26. Avl bal Rs 12,345.67. Call 18002586161 to report fraud."
        " Never share your UPI PIN with anyone."
    )
    truncated = full_body[:150]  # notification EXTRA_TEXT truncation
    assert parser.claim_key(full_body) == parser.claim_key(truncated)
    # Different SMS still produce different keys
    assert parser.claim_key(full_body) != parser.claim_key(
        "Rs.200.00 sent to SOMEONE ELSE via UPI"
    )


def test_amount_matching_tolerates_decimal_formatting_but_rejects_real_mismatches():
    assert parser.is_amount_matching("100", "100.00")
    assert parser.is_amount_matching("1,250.50", "1250.50")
    assert not parser.is_amount_matching("499", "100"), "unrelated debit must not match"
    assert not parser.is_amount_matching("abc", "100"), "non-numeric never matches"


def test_amount_matching_is_paise_exact():
    # The old ±1.0 tolerance let a debit within ₹0.99 confirm this payment.
    assert not parser.is_amount_matching("500.75", "500")
    assert not parser.is_amount_matching("500.99", "500")
    assert not parser.is_amount_matching("499.01", "500")
    assert parser.is_amount_matching("500.00", "500")


def test_success_sms_corpus_is_not_detected_as_failed():
    successes = [
        "Rs.500.00 sent to KIRANA STORE from HDFC Bank A/c **1234 via UPI ref 123456789012 on 20-MAY-26",
        "INR 1,250.50 credited to your ICICI A/c on 20MAY26 from Rahul Sharma via UPI",
        "Rs 12,000 debited from your SBI A/c via UPI 9876543210 on 20/05/26. Ref: 123456789",
        "₹ 250.00 paid to merchant from Axis Bank A/c. UPI Ref: 99887766",
        "100 Rs debited from Kotak A/c **5678. UPI Ref 11223344",
        "Txn successful. Rs 42 transferred. Ref 55667788 -YES Bank",
    ]
    for body in successes:
        assert not parser.detects_failure(body), f"should NOT detect failure: {body}"
