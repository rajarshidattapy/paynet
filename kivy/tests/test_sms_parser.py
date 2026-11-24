# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/test/java/com/paynet/app/payment/sms/SmsTransactionParserTest.kt

"""End-to-end corpus test for paynet/sms/parser.py — the pure bank-SMS
matching pipeline. Every sample below is redacted-but-real-shaped rather
than synthetic, so this corpus is also the reference for what a new bank's
SMS template should look like."""

import re
from collections import namedtuple

from paynet import status as txn_status
from paynet.sms import parser

BankCase = namedtuple("BankCase", "bank sender body amount")

# One representative success SMS per supported bank, deliberately varying
# the amount format (Rs./INR/₹, comma grouping, decimals) and the wording
# across entries so the corpus exercises the full pattern set.
BANK_CORPUS = [
    BankCase(
        "HDFC Bank",
        "VK-HDFCBK",
        "Rs.500.00 sent to KIRANA STORE from HDFC Bank A/c **1234 via UPI ref 512233440091 on 20-MAY-26",
        "500.00",
    ),
    BankCase(
        "ICICI Bank",
        "AD-ICICIB",
        "INR 1,250.50 sent to Rahul Sharma from your ICICI A/c **5566 on 20MAY26 via UPI Ref 778899001122",
        "1250.50",
    ),
    BankCase(
        "State Bank of India",
        "BP-SBIINB",
        "Rs 12,000 debited from your SBI A/c **7788 via UPI to 9876543210 on 20/05/26. Ref: 334455667788",
        "12000",
    ),
    BankCase(
        "Axis Bank",
        "AX-AXISBK",
        "₹250.00 paid to merchant from Axis Bank A/c **9012. UPI Ref: 998877665544",
        "250.00",
    ),
    BankCase(
        "Kotak Bank",
        "KT-KOTAKB",
        "100 Rs debited from Kotak A/c **3456. UPI Ref 112233445566",
        "100",
    ),
    BankCase(
        "Punjab National Bank",
        "PN-PNBSMS",
        "Rs 3,499.00 transferred from PNB A/c **6789 to VPA merchant@okaxis. Ref 223344556677",
        "3499.00",
    ),
    BankCase(
        "Bank of Baroda",
        "BB-BOBIBK",
        "INR 7500.25 sent to Priya Nair from Bank of Baroda A/c **2233 via UPI. Ref 445566778899",
        "7500.25",
    ),
    BankCase(
        "IDFC First Bank",
        "ID-IDFCFB",
        "Rs 999 debited from IDFC A/c **4455 via UPI. Payment of Rs 999 to merchant@ybl. Ref 556677889900",
        "999",
    ),
    BankCase(
        "Yes Bank",
        "YB-YESBNK",
        "Rs 42 transferred from Yes Bank A/c **6677 via UPI Ref 667788990011. Txn successful.",
        "42",
    ),
    BankCase(
        "Paytm Payments Bank",
        "PT-PAYTMB",
        "Rs.300.00 paid to Rohit Kumar from Paytm Payments Bank A/c via UPI. Ref 778899001122",
        "300.00",
    ),
    BankCase(
        "Union Bank",
        "UB-UNIONB",
        "Rs 15,000 debited from Union Bank A/c **8899 via UPI to 9988776655. Ref 889900112233",
        "15000",
    ),
    BankCase(
        "Canara Bank",
        "CN-CANBNK",
        "INR 620.75 sent to Anita Desai from Canara Bank A/c **1122 via UPI. Ref 990011223344",
        "620.75",
    ),
    BankCase(
        "IndusInd Bank",
        "IB-INDUSB",
        "Rs 88 debited from IndusInd Bank A/c **3344 via UPI. Payment of Rs 88 for Coffee. Ref 001122334455",
        "88",
    ),
    BankCase(
        "Federal Bank",
        "FB-FEDBNK",
        "Rs 5,000.00 transferred from Federal Bank A/c **5566 to merchant@fbl via UPI. Ref 112233445566",
        "5000.00",
    ),
    # Dual-verb templates: the bank narrates both sides of one payment, so
    # the body carries "debited" AND "credited". These are ordinary
    # outgoing confirmations and must parse as DEBIT.
    BankCase(
        "ICICI Bank",
        "AD-ICICIB",
        "ICICI Bank Acct XX556 debited for Rs 500.00 on 29-Jul-26; KIRANA STORE credited. UPI:512233440091",
        "500.00",
    ),
    BankCase(
        "Union Bank",
        "VM-UNIONB",
        "Rs.2,340.00 debited from Union Bank A/c **8899 and credited to merchant@ubi. UPI Ref 445566778899",
        "2340.00",
    ),
]


def test_parses_a_success_sms_for_every_supported_bank():
    for case in BANK_CORPUS:
        result = parser.parse(case.sender, case.body, expected_amount=None)
        assert result is not None, f"expected a match for {case.bank}: {case.body}"
        assert result.bank_name == case.bank, case.body
        assert result.amount == case.amount, case.body
        assert result.status == txn_status.SUCCESS, case.body
        assert result.transaction_type == "DEBIT", case.body


def test_parses_a_failure_sms_across_several_banks():
    cases = [
        BankCase(
            "HDFC Bank",
            "VK-HDFCBK",
            "Payment of Rs 500 failed. Ref 123456789012. -HDFC Bank",
            "500",
        ),
        BankCase(
            "ICICI Bank",
            "AD-ICICIB",
            "Your UPI payment of Rs.75 could not be processed. Please retry. -ICICI Bank",
            "75",
        ),
        BankCase(
            "State Bank of India",
            "BP-SBIINB",
            "Rs 120 reversed to your SBI account **5678. Ref 998877",
            "120",
        ),
    ]
    for case in cases:
        result = parser.parse(case.sender, case.body, expected_amount=None)
        assert result is not None, f"expected a match for {case.bank}: {case.body}"
        assert result.status == txn_status.FAILED, case.body


def test_incoming_credit_sms_is_parsed_with_sender_info_not_recipient_info():
    result = parser.parse(
        sender="AD-ICICIB",
        body="INR 1,500.00 credited to ICICI A/c **5566 from Sanjay Mehta via UPI. Ref 665544332211",
        expected_amount=None,
    )
    assert result is not None
    assert result.transaction_type == "CREDIT"
    assert result.status == txn_status.SUCCESS
    assert result.amount == "1500.00"


def test_dual_verb_debit_template_confirms_the_payment_it_belongs_to():
    result = parser.parse(
        sender="AD-ICICIB",
        body="ICICI Bank Acct XX556 debited for Rs 500.00 on 29-Jul-26; KIRANA STORE credited. UPI:512233440091",
        expected_amount="500",
    )
    assert result is not None, "a dual-verb debit is our confirmation"
    assert result.transaction_type == "DEBIT"
    assert result.status == txn_status.SUCCESS
    assert result.amount == "500.00"


def test_dual_verb_debit_for_a_different_amount_is_still_dropped():
    result = parser.parse(
        sender="AD-ICICIB",
        body="ICICI Bank Acct XX556 debited for Rs 900.00 on 29-Jul-26; OTHER SHOP credited. UPI:512233440099",
        expected_amount="500",
    )
    assert result is None, "a dual-verb debit for another amount is not our confirmation"


def test_debit_verbs_win_over_credit_words_when_a_body_carries_both():
    assert parser.detect_transaction_type("A/c XX1 debited Rs 10; payee credited") == "DEBIT"
    assert parser.detect_transaction_type("Rs 10 credited to A/c XX1 by UPI") == "CREDIT"


def test_non_upi_debit_alert_still_qualifies_via_the_generic_amount_fallback():
    result = parser.parse(
        sender="SB-SBIINB",
        body="Rs 2000 withdrawn from SBI ATM Card **9021 on 20-MAY-26. Avl Bal Rs 34,210.00.",
        expected_amount=None,
    )
    assert result is not None
    assert result.bank_name == "State Bank of India"
    assert result.amount == "2000"


def test_amount_formats():
    assert parser.extract_amount("Rs.500.00 sent to KIRANA STORE") == "500.00"
    assert parser.extract_amount("INR 1,250.50 credited") == "1250.50"
    assert parser.extract_amount("₹250.00 paid to merchant") == "250.00"
    # Indian numbering groups by lakh/crore after the first three digits.
    assert parser.extract_amount("Rs 1,00,000.00 transferred to merchant") == "100000.00"


def test_mismatched_amount_debit_is_not_this_payments_confirmation():
    result = parser.parse(
        sender="VK-HDFCBK",
        body="Rs.100.00 sent to KIRANA STORE from HDFC Bank A/c **1234 via UPI ref 512233440091",
        expected_amount="500",
    )
    assert result is None, "a debit for a different amount is not our confirmation"


def test_unrelated_failure_alert_with_mismatched_amount_never_confirms():
    # The money-loss blocker: while a Rs.500 payment is pending, an
    # unrelated Rs.200 decline must NOT be recorded as this payment's FAILED.
    result = parser.parse(
        sender="VK-HDFCBK",
        body="HDFC Bank card txn of Rs.200.00 at AMAZON declined: insufficient balance. Ref 700000000001",
        expected_amount="500",
    )
    assert result is None, "a mismatched-amount failure alert is not this payment's failure"


def test_failure_alert_with_a_matching_amount_is_recorded_as_failed():
    result = parser.parse(
        sender="VK-HDFCBK",
        body="Payment of Rs.500.00 to KIRANA STORE failed. UPI ref 512233440091 -HDFC Bank",
        expected_amount="500",
    )
    assert result is not None
    assert result.status == txn_status.FAILED


def test_expected_amount_match_is_success():
    result = parser.parse(
        sender="VK-HDFCBK",
        body="Rs.500.00 sent to KIRANA STORE from HDFC Bank A/c **1234 via UPI ref 512233440091",
        expected_amount="500",
    )
    assert result is not None
    assert result.status == txn_status.SUCCESS


def test_sms_with_no_bank_affiliation_and_no_amount_does_not_match():
    result = parser.parse(
        sender="JD-BIGSALE",
        body="Flash sale starts now! Check the app for today's deals.",
        expected_amount=None,
    )
    assert result is None


def test_claim_key_converges_for_a_full_body_and_its_truncated_form():
    full_body = (
        BANK_CORPUS[0].body
        + ". Avl bal Rs 12,345.67. Call 18002586161 to report fraud."
        + " Never share your UPI PIN with anyone."
    )
    truncated = full_body[:140]  # simulates a notification EXTRA_TEXT cutoff
    assert parser.claim_key(full_body) == parser.claim_key(truncated)


def test_promo_sms_containing_the_word_yes_never_enters_the_pipeline():
    result = parser.parse(
        sender="JD-PROMO4U",
        body="Say YES to win Rs 5000! Reply YES to enter the lucky draw today.",
        expected_amount="5000",
    )
    assert result is None

    # The real thing still matches — by sender header...
    assert parser.detect_bank("YB-YESBNK", "Rs 100 debited") == "Yes Bank"
    # ...and by full phrase in the body.
    assert parser.detect_bank("XX-UNKNOWN", "Rs 100 debited from your Yes Bank A/c") == "Yes Bank"


def test_balance_first_template_extracts_the_transaction_amount():
    result = parser.parse(
        sender="VK-SBIUPI",
        body="Avl Bal Rs 34,210.00 in A/c X1234. Rs 2000 debited for UPI txn 512233440091 -SBI",
        expected_amount=None,
    )
    assert result is not None
    assert result.amount == "2000"


def test_balance_only_body_still_extracts_something():
    assert parser.extract_amount("Avl bal Rs 12,345.67 in your account") == "12345.67"


def test_transaction_id_is_deterministic_under_an_injected_clock():
    body = "Flash cashback of Rs 200 credited to your wallet."
    fixed_clock = lambda: 1_700_000_000_000
    fixed_suffix = lambda: 4321

    first = parser.parse("YB-YESBNK", body, None, fixed_clock, fixed_suffix)
    second = parser.parse("YB-YESBNK", body, None, fixed_clock, fixed_suffix)

    assert first is not None
    assert first.transaction_id == "TXN17000000000004321"
    assert first.transaction_id == second.transaction_id


def test_transaction_id_from_a_reference_carries_the_injected_clock():
    result = parser.parse(
        sender="VK-HDFCBK",
        body="Rs.500.00 sent to KIRANA STORE from HDFC Bank A/c **1234 via UPI ref 512233440091",
        expected_amount=None,
        clock=lambda: 42,
    )
    assert result is not None
    # Assert the reference itself, not just the clock suffix.
    assert result.transaction_id == "512233440091_42"


def test_a_reference_is_read_from_the_banks_ref_number_not_inside_the_word_paid():
    result = parser.parse(
        sender="VK-HDFCBK",
        body="Rs.1250.00 paid to SHARMA STORE from HDFC Bank A/c **1234 failed. "
        "UPI Ref No 512233440091. Not you? Call 18002586161",
        expected_amount=None,
        clock=lambda: 42,
    )
    assert result is not None
    assert result.transaction_id == "512233440091_42"
    assert result.status == txn_status.FAILED


def test_failure_templates_do_not_absorb_status_words_into_the_payee_name():
    bodies = [
        "Rs.200.00 paid to Kirana Store has failed. HDFC Bank",
        "Rs.200 paid to Kirana Store has failed",
        "Payment of Rs 200 sent to Kirana Store was declined",
    ]
    for body in bodies:
        result = parser.parse("VK-HDFCBK", body, None)
        assert result is not None, f"expected a match for: {body}"
        assert result.recipient_name == "Kirana Store", (
            f"payee must stop before the status words: {body}"
        )


def test_failure_templates_with_no_verb_before_the_payee_stop_at_status_words():
    cases = {
        "Your payment of Rs.850.00 to BIG MERCHANT has failed. Ref 850999888777":
            "Big Merchant",
        "Payment of Rs.300.00 to SHARMA GENERAL STORE was declined by your bank. Ref 300111222":
            "Sharma General Store",
        "Rs.450.00 to CORNER TEA STALL could not be processed. Ref 450111":
            "Corner Tea Stall",
    }
    for body, expected in cases.items():
        result = parser.parse("VK-HDFCBK", body, None)
        assert result is not None, f"expected a match for: {body}"
        assert result.recipient_name == expected, (
            f"payee must stop before the status words: {body}"
        )


def test_bare_to_name_fallback_still_resolves_date_and_ref_terminated_payees():
    cases = {
        "Rs.250.00 debited from A/c XX9999 to CAFE COFFEE DAY on 09-Aug-26. Ref 250333444":
            "Cafe Coffee Day",
        "Rs.75.00 debited from A/c XX9999 to METRO STORE dated 09-Aug-26":
            "Metro Store",
    }
    for body, expected in cases.items():
        result = parser.parse("VK-HDFCBK", body, None)
        assert result is not None, f"expected a match for: {body}"
        assert result.recipient_name == expected, f"payee must survive intact: {body}"


def test_multi_word_payee_names_are_not_truncated_at_the_first_space():
    cases = {
        "Rs.500.00 sent to KIRANA STORE from HDFC Bank A/c **1234 via UPI ref 512233440091":
            "Kirana Store",
        "Rs.100000.00 sent to BIG MERCHANT from HDFC Bank A/c **1234 via UPI ref 512233441000":
            "Big Merchant",
        "Rs.300 sent to TEA STALL from HDFC Bank A/c **1234 via UPI ref 99":
            "Tea Stall",
    }
    for body, expected in cases.items():
        result = parser.parse("VK-HDFCBK", body, None)
        assert result is not None, f"expected a match for: {body}"
        assert result.recipient_name == expected, (
            f"payee must not stop at the first space: {body}"
        )


def test_payee_names_beginning_with_a_status_word_survive_intact():
    cases = {
        "Rs.100 paid to Hasty Traders via UPI": "Hasty Traders",
        "Rs.100 paid to Hasmukh Patel via UPI": "Hasmukh Patel",
        "Rs.100 paid to Ismail Khan via UPI": "Ismail Khan",
        "Rs.100 paid to Notandas Stores via UPI": "Notandas Stores",
        "Rs.100 sent to Arewa Foods via UPI": "Arewa Foods",
        "Rs.100 sent to Isabella Fernandes via UPI": "Isabella Fernandes",
    }
    for body, expected in cases.items():
        result = parser.parse("VK-HDFCBK", body, None)
        assert result is not None, f"expected a match for: {body}"
        assert result.recipient_name == expected


def test_a_message_carrying_an_amount_but_no_transaction_verb_never_confirms():
    not_payments = [
        ("AD-BIGBAZ", "Mega sale! Get products worth Rs.300 free. Shop now at bigbazaar.example"),
        ("VM-HDFCBK", "456 is your OTP for HDFC Bank. Rs.456 txn. Do not share with anyone."),
        ("VK-HDFCBK", "Your HDFC Bank A/c **1234 Avl Bal is Rs.600.00 as on 05-Aug-26."),
    ]
    for sender, body in not_payments:
        amount = re.search(r"Rs\.?([0-9]+)", body).group(1)
        assert parser.parse(sender, body, amount) is None, (
            f"must not confirm a payment: {body}"
        )


def test_avl_bal_is_rs_x_is_not_a_payment_even_at_the_exact_expected_amount():
    assert (
        parser.parse(
            "VK-HDFCBK",
            "Your HDFC Bank A/c **1234 Avl Bal is Rs.600.00 as on 05-Aug-26.",
            "600",
        )
        is None
    )


def test_a_genuine_debit_still_confirms_through_the_gate():
    parsed = parser.parse(
        "PN-PNBSMS",
        "Rs 3,499.00 transferred from PNB A/c **6789 to VPA merchant@okaxis. Ref 223344556677",
        "3499",
    )
    assert parsed is not None
    assert parsed.status == txn_status.SUCCESS


def test_dual_verb_template_resolves_the_payee_not_unknown():
    parsed = parser.parse(
        "AD-ICICIB",
        "ICICI Bank Acct XX556 debited for Rs 500.00 on 05-Aug-26; KIRANA STORE credited. UPI:512233440091",
        "500",
    )
    assert parsed is not None
    assert parsed.transaction_type == "DEBIT"
    assert parsed.recipient_name == "Kirana Store"
