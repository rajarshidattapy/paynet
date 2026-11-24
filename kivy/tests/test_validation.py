# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/test/java/com/paynet/app/payment/PaymentInputValidatorTest.kt

"""Guards the two user inputs — recipient number and amount — before any
dial is attempted."""

from paynet.payment.validation import is_valid_amount, is_valid_phone_number


def test_valid_10_digit_numbers_are_accepted():
    assert is_valid_phone_number("9876543210")
    assert is_valid_phone_number("1234567890")


def test_phone_numbers_with_a_leading_zero_are_rejected():
    assert not is_valid_phone_number("0123456789")


def test_phone_numbers_of_the_wrong_length_are_rejected():
    assert not is_valid_phone_number("98765")
    assert not is_valid_phone_number("98765432109")


def test_non_numeric_blank_and_none_phone_numbers_are_rejected():
    assert not is_valid_phone_number("98765abcde")
    assert not is_valid_phone_number("98765 4321")
    assert not is_valid_phone_number("")
    assert not is_valid_phone_number(None)


def test_amounts_within_the_range_are_accepted():
    assert is_valid_amount("1")
    assert is_valid_amount("500")
    assert is_valid_amount("100000")
    assert is_valid_amount("99.99")


def test_amounts_below_minimum_or_above_ceiling_are_rejected():
    assert not is_valid_amount("0")
    assert not is_valid_amount("0.5")
    assert not is_valid_amount("100001")


def test_non_numeric_blank_and_none_amounts_are_rejected():
    assert not is_valid_amount("abc")
    assert not is_valid_amount("")
    assert not is_valid_amount(None)
