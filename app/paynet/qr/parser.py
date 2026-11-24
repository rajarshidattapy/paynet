# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay

"""Strict UPI QR parser — 1:1 port of
features/qr_scanner/domain/QRCodeParser.kt plus the UPIData data class
(data/UPIData.kt) and the messageFor UI-edge mapping.

Accepts exactly two shapes:
 1. A ``upi://`` URI (NPCI QR spec) with a structurally valid ``pa`` (VPA)
 2. A bare VPA string (some merchants print raw-VPA QRs)

Everything else is Invalid with a reason. The old behaviour — regex-fishing
``pa=`` out of arbitrary text and treating any string containing "@" as a
VPA — silently turned random QR codes into "payees" and sent users into a
doomed USSD flow.
"""

import enum
import re
import urllib.parse
from dataclasses import dataclass

# NPCI VPA shape: local part (letters/digits/._-), an @, and an
# alphanumeric PSP handle starting with a letter.
VPA_REGEX = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z][a-zA-Z0-9]{1,64}$")

# Generic input ceiling for a QR-initiated payment.
MAX_QR_AMOUNT = 100_000.0

# At most two decimal places per the NPCI spec.
_AMOUNT_FORMAT = re.compile(r"^[0-9]+(\.[0-9]{1,2})?$")

# Kotlin \p{Cntrl}: C0/C1 control characters.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


@dataclass
class UPIData:
    vpa: str
    payee_name: str
    amount: str
    transaction_note: str
    currency: str


class Reason(enum.Enum):
    """Why a scanned code was rejected. An enum, not a sentence: the parser
    is pure and unit-tested, and the copy shown over the live camera lives
    with the rest of the strings; message_for does the mapping at the UI
    edge."""

    EMPTY = "EMPTY"
    NOT_A_UPI_QR = "NOT_A_UPI_QR"
    MALFORMED = "MALFORMED"
    NO_PAYEE_ADDRESS = "NO_PAYEE_ADDRESS"
    INVALID_PAYEE_ADDRESS = "INVALID_PAYEE_ADDRESS"
    INVALID_AMOUNT = "INVALID_AMOUNT"


@dataclass
class Valid:
    data: UPIData


@dataclass
class Invalid:
    reason: Reason


# ParseResult = Union[Valid, Invalid]

# qr_reason_* strings (strings.xml).
STR_REASON_EMPTY = "Scan a UPI payment QR code."
STR_REASON_NOT_UPI = "Scan a UPI payment QR code."
STR_REASON_MALFORMED = "This QR could not be read. Try another UPI QR."
STR_REASON_NO_PAYEE = "This QR does not include a UPI ID."
STR_REASON_INVALID_PAYEE = "This QR contains an invalid UPI ID."
STR_REASON_INVALID_AMOUNT = "This QR contains an invalid amount."

_REASON_MESSAGES = {
    Reason.EMPTY: STR_REASON_EMPTY,
    Reason.NOT_A_UPI_QR: STR_REASON_NOT_UPI,
    Reason.MALFORMED: STR_REASON_MALFORMED,
    Reason.NO_PAYEE_ADDRESS: STR_REASON_NO_PAYEE,
    Reason.INVALID_PAYEE_ADDRESS: STR_REASON_INVALID_PAYEE,
    Reason.INVALID_AMOUNT: STR_REASON_INVALID_AMOUNT,
}


def message_for(reason: Reason) -> str:
    """The UI edge where a Reason becomes the sentence shown in the
    scanner's inline banner."""
    return _REASON_MESSAGES[reason]


def _query_param(query: str, key: str):
    """Android Uri.getQueryParameter: first match wins, percent-decoded,
    '+' is NOT decoded to a space, a bare 'key' yields ''."""
    if not query:
        return None
    for pair in query.split("&"):
        if not pair:
            continue
        name, eq, value = pair.partition("=")
        if urllib.parse.unquote(name) == key:
            return urllib.parse.unquote(value) if eq else ""
    return None


def parse(qr_code: str):
    raw = qr_code.strip()
    if not raw:
        return Invalid(Reason.EMPTY)

    if raw.lower().startswith("upi://"):
        return _parse_upi_uri(raw)
    if VPA_REGEX.match(raw):
        return Valid(UPIData(vpa=raw, payee_name="", amount="",
                             transaction_note="", currency="INR"))
    return Invalid(Reason.NOT_A_UPI_QR)


def _parse_upi_uri(raw: str):
    try:
        parts = urllib.parse.urlsplit(raw)
    except ValueError:
        return Invalid(Reason.MALFORMED)

    vpa = (_query_param(parts.query, "pa") or "").strip()
    if not vpa:
        return Invalid(Reason.NO_PAYEE_ADDRESS)
    if not VPA_REGEX.match(vpa):
        return Invalid(Reason.INVALID_PAYEE_ADDRESS)

    amount_param = (_query_param(parts.query, "am") or "").strip()
    if amount_param:
        try:
            amount = float(amount_param)
        except ValueError:
            return Invalid(Reason.INVALID_AMOUNT)
        if amount <= 0 or amount > MAX_QR_AMOUNT:
            return Invalid(Reason.INVALID_AMOUNT)
        if not _AMOUNT_FORMAT.match(amount_param):
            return Invalid(Reason.INVALID_AMOUNT)

    payee_name = _CONTROL_CHARS.sub(
        "", (_query_param(parts.query, "pn") or "").strip())[:99]
    note = (_query_param(parts.query, "tn") or "").strip()[:99]

    return Valid(UPIData(vpa=vpa, payee_name=payee_name, amount=amount_param,
                         transaction_note=note, currency="INR"))


def is_valid_upi_qr_code(qr_code: str) -> bool:
    return isinstance(parse(qr_code), Valid)


def parse_upi_qr_code(qr_code: str) -> UPIData:
    """Legacy adapter for call sites built around "empty VPA means invalid".
    Prefer parse() — it carries the rejection reason."""
    result = parse(qr_code)
    if isinstance(result, Valid):
        return result.data
    return UPIData(vpa="", payee_name="", amount="", transaction_note="",
                   currency="INR")
