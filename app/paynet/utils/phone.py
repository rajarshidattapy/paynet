# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/utils/PhoneNumberUtils.kt and
# app/src/main/java/com/paynet/app/utils/PaymentPhoneInput.kt

"""Phone number normalization, display formatting, and payment-input
normalization. Accepts familiar Indian phone formatting without guessing a
destination from arbitrary digits."""

import re
from typing import NamedTuple, Optional

from paynet import constants

_LOCAL_LENGTH = 10
_COUNTRY_CODE = "91"
_TRUNK_PREFIX = "0"
_COMPLETE_NUMBER_PATTERN = re.compile(constants.PHONE_NUMBER_PATTERN)

_SEPARATORS = frozenset(" \t\r\n-()" + "\u00a0\u202f\u2010\u2011\u2013")


def normalize_phone_number(phone_number: Optional[str]) -> Optional[str]:
    """Strip all non-digit characters; None when the input is null/blank."""
    if not phone_number or not phone_number.strip():
        return None
    return re.sub(r"[^0-9]", "", phone_number)


def format_phone_for_display(phone_number: Optional[str], last_digits: int = 4) -> str:
    """'••••••0000' style masking for display."""
    if not phone_number or not phone_number.strip():
        return "••••••0000"
    normalized = normalize_phone_number(phone_number)
    if normalized is None:
        return "••••••0000"
    if len(normalized) >= last_digits:
        return "•" * (len(normalized) - last_digits) + normalized[-last_digits:]
    return phone_number


class TextRange(NamedTuple):
    start: int
    end: int


class TextValue(NamedTuple):
    """Minimal stand-in for Compose TextFieldValue: text + selection +
    optional composition (all offsets into text)."""

    text: str
    selection: TextRange
    composition: Optional[TextRange] = None


def _is_separator(char: str) -> bool:
    return char in _SEPARATORS


def _normalize_international(text: str) -> Optional[str]:
    digits = text[1:]
    has_indian_prefix = _COUNTRY_CODE.startswith(digits) or digits.startswith(_COUNTRY_CODE)
    if (
        any(c not in "0123456789" for c in digits)
        or not has_indian_prefix
        or len(digits) > _LOCAL_LENGTH + len(_COUNTRY_CODE)
    ):
        return None
    if len(digits) == _LOCAL_LENGTH + len(_COUNTRY_CODE):
        return digits[len(_COUNTRY_CODE):]
    return text


def _normalize_compact(text: str) -> Optional[str]:
    if text.startswith("+"):
        return _normalize_international(text)
    if any(c not in "0123456789" for c in text):
        return None
    if len(text) <= _LOCAL_LENGTH:
        return text
    if len(text) == _LOCAL_LENGTH + len(_TRUNK_PREFIX) and text.startswith(_TRUNK_PREFIX):
        return text[len(_TRUNK_PREFIX):]
    if len(text) == _LOCAL_LENGTH + len(_COUNTRY_CODE) and text.startswith(_COUNTRY_CODE):
        return text[len(_COUNTRY_CODE):]
    if len(text) < _LOCAL_LENGTH + len(_COUNTRY_CODE) and text.startswith(_COUNTRY_CODE):
        return text
    return None


def normalize(value: TextValue) -> Optional[TextValue]:
    """Normalize an edit. None rejects the edit; incomplete accepted input
    remains editable but cannot be submitted."""
    compact = "".join(c for c in value.text if not _is_separator(c))
    normalized = _normalize_compact(compact)
    if normalized is None:
        return None
    prefix_length = len(compact) - len(normalized)

    def offset(original: int) -> int:
        non_separators = sum(1 for c in value.text[:original] if not _is_separator(c))
        return min(max(non_separators - prefix_length, 0), len(normalized))

    composition = None
    if value.composition is not None:
        composition = TextRange(offset(value.composition.start), offset(value.composition.end))

    return TextValue(
        text=normalized,
        selection=TextRange(offset(value.selection.start), offset(value.selection.end)),
        composition=composition,
    )


def complete_number(text: str) -> Optional[str]:
    """The contact picker must use the same complete-number rules as manual
    entry."""
    normalized = _normalize_compact("".join(c for c in text if not _is_separator(c)))
    if normalized is not None and _COMPLETE_NUMBER_PATTERN.fullmatch(normalized):
        return normalized
    return None
