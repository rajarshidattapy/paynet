# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/test/java/com/paynet/app/payment/Upi123CallStringBuilderTest.kt

"""Locks the exact DTMF dial string for the UPI 123Pay IVR flow.
A malformed string here dials a wrong DTMF sequence against a live
payment IVR — these tests are the contract."""

from paynet.payment.call_string import Invalid, Valid, build


def build_valid(service="08045163666", phone="9876543210", amount="100"):
    return build(service, phone, amount)


def test_golden_call_string_is_byte_identical():
    assert build_valid() == Valid("tel:08045163666,,1,9876543210,,100,,1")


def test_custom_service_number_is_preserved():
    assert build_valid(service="08045163581") == Valid(
        "tel:08045163581,,1,9876543210,,100,,1"
    )


def test_maximum_allowed_amount_builds():
    # The 123Pay IVR accepts amounts strictly below Rs 5,000.
    assert build_valid(amount="4999") == Valid(
        "tel:08045163666,,1,9876543210,,4999,,1"
    )


def test_amount_above_123pay_cap_is_rejected():
    assert isinstance(build_valid(amount="5000"), Invalid)
    assert isinstance(build_valid(amount="10000"), Invalid)


def test_zero_and_negative_amounts_are_rejected():
    assert isinstance(build_valid(amount="0"), Invalid)
    assert isinstance(build_valid(amount="-5"), Invalid)


def test_decimal_amounts_are_rejected():
    # IVR consumes whole-rupee digits
    assert isinstance(build_valid(amount="100.50"), Invalid)


def test_non_numeric_amount_is_rejected():
    assert isinstance(build_valid(amount="abc"), Invalid)
    assert isinstance(build_valid(amount=""), Invalid)


def test_phone_number_must_be_exactly_ten_digits_not_starting_with_zero():
    assert isinstance(build_valid(phone="987654321"), Invalid)
    assert isinstance(build_valid(phone="98765432101"), Invalid)
    assert isinstance(build_valid(phone="0876543210"), Invalid)
    assert isinstance(build_valid(phone=""), Invalid)


def test_dtmf_injection_attempts_are_neutralised_or_rejected():
    assert isinstance(build_valid(phone="98765#4321"), Invalid)
    assert isinstance(build_valid(amount="1,,9999999999,,1"), Invalid)
    assert isinstance(build_valid(amount="100;rm"), Invalid)

    # Formatting characters that strip down to a valid number are fine.
    assert build_valid(phone="98765-43210") == Valid(
        "tel:08045163666,,1,9876543210,,100,,1"
    )


def test_invalid_service_number_is_rejected():
    assert isinstance(build_valid(service="12345"), Invalid)
    assert isinstance(build_valid(service=""), Invalid)
