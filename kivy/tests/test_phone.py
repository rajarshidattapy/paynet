# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/test/java/com/paynet/app/utils/PaymentPhoneInputTest.kt
# (Compose TextFieldValue adapted to paynet.utils.phone.TextValue; the
# Compose Saver round-trip case has no Python analogue and is not ported.)

from paynet.utils.phone import (
    TextRange,
    TextValue,
    complete_number,
    format_phone_for_display,
    normalize,
    normalize_phone_number,
)

LOCAL_NUMBER = "9876543210"


def _normalize(text):
    return normalize(TextValue(text, TextRange(len(text), len(text))))


def test_pasted_indian_formats_become_the_same_complete_destination():
    inputs = [
        LOCAL_NUMBER,
        "98765 43210",
        "(98765)-43210",
        "+91 98765\u201143210",
        "+91 (98765) 43210",
        "91-98765-43210",
        "09876543210",
        "0 (98765) 43210",
        " +91\u00a098765\u202f43210 ",
        "+91 98765\u201143210",
        "\n\t+91 98765\n43210\r\n",
    ]
    for raw in inputs:
        assert complete_number(raw) == LOCAL_NUMBER, raw
        result = _normalize(raw)
        assert result is not None, raw
        assert result.text == LOCAL_NUMBER, raw
        assert result.selection == TextRange(len(LOCAL_NUMBER), len(LOCAL_NUMBER)), raw


def test_rejects_foreign_numbers_extensions_and_mixed_characters():
    inputs = [
        "+1 9876543210", "+44 9876543210", "449876543210", "00919876543210",
        "1239876543210", "98765432101", "9876543210 ext 2", "call 9876543210",
        "9876543210#", "*99#", "98765;43210", "98765,43210", "9+876543210",
        "+9198765432100", "98765/43210", "९८७६५४३२१०", "9876543210\n9876543210",
    ]
    for raw in inputs:
        assert _normalize(raw) is None, raw
        assert complete_number(raw) is None, raw


def test_ten_digit_numbers_beginning_with_91_keep_their_own_digits():
    assert complete_number("9123456780") == "9123456780"
    assert complete_number("+91 9123456780") == "9123456780"


def test_partial_typing_and_deleting_remain_editable_without_becoming_payable():
    partials = ["", "9", "98765", "0", "0987654321", "+", "+9", "+91",
                "+91 98765", "91987654321"]
    for raw in partials:
        assert _normalize(raw) is not None, raw
        assert complete_number(raw) is None, raw

    value = TextValue("", TextRange(0, 0))
    for digit in "+919876543210":
        result = _normalize(value.text + digit)
        assert result is not None
        value = result
    assert value.text == LOCAL_NUMBER
    while value.text:
        result = _normalize(value.text[:-1])
        assert result is not None
        value = result
    assert value.text == ""


def test_complete_numbers_still_require_the_nonzero_ten_digit_pattern():
    assert complete_number("0000000000") is None
    assert complete_number("+91 0000000000") is None
    assert complete_number("1234567890") == "1234567890"


def test_normalization_maps_mid_text_and_reversed_selection():
    formatted = "+91 (98765) 43210"
    reversed_selection = TextRange(formatted.index(")"), formatted.index("(") + 1)
    result = normalize(TextValue(formatted, reversed_selection))
    assert result is not None
    assert result.text == LOCAL_NUMBER
    assert result.selection == TextRange(LOCAL_NUMBER.index("4"), 0)

    spaced = "98765 43210"
    after_space = TextRange(spaced.index(" ") + 1, spaced.index(" ") + 1)
    middle = normalize(TextValue(spaced, after_space))
    assert middle is not None
    assert middle.selection == TextRange(LOCAL_NUMBER.index("4"), LOCAL_NUMBER.index("4"))


def test_composing_region_is_mapped_along_with_cursor():
    spaced = "98765 43210"
    composed_suffix = TextRange(spaced.index("4"), len(spaced))
    result = normalize(
        TextValue(spaced, TextRange(len(spaced), len(spaced)), composed_suffix)
    )
    assert result is not None
    assert result.composition == TextRange(LOCAL_NUMBER.index("4"), len(LOCAL_NUMBER))
    assert result.selection == TextRange(len(LOCAL_NUMBER), len(LOCAL_NUMBER))


def test_normalize_phone_number_strips_non_digits():
    assert normalize_phone_number("+91 98765-43210") == "919876543210"
    assert normalize_phone_number("") is None
    assert normalize_phone_number(None) is None


def test_format_phone_for_display_masks_all_but_the_tail():
    assert format_phone_for_display("9876543210") == "••••••3210"
    assert format_phone_for_display("") == "••••••0000"
    assert format_phone_for_display(None) == "••••••0000"
