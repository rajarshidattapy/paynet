# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/test/java/com/paynet/app/utils/CurrencyFormatTest.kt

"""Pins the Indian 3-2-2 grouping rule."""

from paynet.utils.currency import inr


def test_groups_lakhs_in_the_indian_3_2_2_pattern():
    assert inr("100000") == "1,00,000.00"
    assert inr("1234567") == "12,34,567.00"


def test_groups_thousands_the_same_way_western_formatting_would():
    assert inr("1000") == "1,000.00"
    assert inr("99999") == "99,999.00"


def test_always_shows_exactly_two_decimal_places():
    assert inr("500") == "500.00"
    assert inr("500.5") == "500.50"
    assert inr("500.75") == "500.75"


def test_string_and_number_inputs_agree():
    for raw in ("1", "500.5", "100000", "1234567.89"):
        assert inr(raw) == inr(float(raw)), f"inputs disagreed for {raw}"


def test_small_amounts_carry_no_separator():
    assert inr("1") == "1.00"
    assert inr("0.01") == "0.01"
    assert inr("999") == "999.00"


def test_keeps_grouping_in_twos_above_a_lakh():
    # 10 lakh, 1 crore, 100 crore
    assert inr("1000000") == "10,00,000.00"
    assert inr("10000000") == "1,00,00,000.00"
    assert inr("1000000000") == "1,00,00,00,000.00"


def test_negative_amounts_keep_their_sign_outside_the_grouping():
    assert inr("-100000") == "-1,00,000.00"
    assert inr(-500.0) == "-500.00"


def test_rounds_half_even_rather_than_truncating():
    assert inr("0.125") == "0.12"
    assert inr("0.135") == "0.14"
    assert inr("100000.123") == "1,00,000.12"
    assert inr("100000.126") == "1,00,000.13"


def test_a_non_numeric_amount_is_passed_through_untouched():
    assert inr("") == ""
    assert inr("N/A") == "N/A"
    # commas already in; not re-parsed (matches Kotlin toBigDecimalOrNull)
    assert inr("1,000") == "1,000"
