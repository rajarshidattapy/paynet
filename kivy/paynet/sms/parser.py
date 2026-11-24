# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/payment/sms/SmsTransactionParser.kt

"""Bank-SMS transaction detection — the original, field-proven matching
logic. Deliberately PERMISSIVE: substring bank keywords over sender and
body, a generic shortcode fallback, and "any success indicator OR an
amount" qualification. This matched real bank templates in the field, so
it is kept verbatim rather than replaced with stricter rules that risk
missing genuine confirmations.

Pure and platform-free by design: no prefs, no singleton, no ambient clock
— parse() takes a clock and a random-suffix provider as parameters so
callers (and tests) can make transaction-ID generation deterministic.
paynet/sms/detector.py is the stateful orchestrator around this: it owns
the operation window and cross-pipeline SMS dedup, and delegates all
actual message matching here.
"""

import math
import random
import re
import time
from dataclasses import dataclass
from typing import Callable, Optional

from paynet import status as txn_status


@dataclass
class SimpleTransaction:
    transaction_id: str
    amount: str
    status: str
    bank_name: str
    # Privacy-safe summary built from extracted fields — never the raw SMS body.
    sms_excerpt: str
    timestamp: int = 0
    upi_id: Optional[str] = None
    transaction_type: str = "DEBIT"
    recipient_name: Optional[str] = None  # who money was sent to
    phone_number: Optional[str] = None  # phone number if available


# Words that can follow a payee name in a bank template but are never part
# of it. Without them a failure template — "Rs.200 paid to Kirana Store has
# failed" — has nothing to stop the lazy name group before end-of-string,
# so the row renders its payee as "Kirana Store Has Failed".
#
# The \b at the use site is what keeps real names that merely *begin* with
# one of these intact: Hasty Traders, Hasmukh Patel, Ismail Khan,
# Notandas Stores, Arewa Foods.
_NAME_STOP_WORDS = (
    "has|have|had|was|were|is|are|will|could|did|does|failed|declined|unsuccessful|not|due"
)

# Where a payee name ends: a following keyword, or punctuation, or the end
# of the body. Deliberately NOT a bare \s — that stops at the first space
# and truncates every multi-word payee to one word ("KIRANA STORE" ->
# "Kirana"). `from` is included because "sent to NAME from <bank> A/c ..."
# is the most common Indian debit template.
_NAME_TERMINATOR = (
    r"(?:\s+(?:via|@|on|dated|for|from|to|UPI|Ref)\b|\s+(?:"
    + _NAME_STOP_WORDS
    + r")\b|\.|,|;|$)"
)

# Name extraction patterns - CASE-INSENSITIVE
_RECIPIENT_PATTERNS = [
    # "sent to NAME" or "paid to NAME"
    r"(?:sent|paid|transferred)\s+to\s+([a-zA-Z][a-zA-Z\s\.]+?)" + _NAME_TERMINATOR,
    # "to NAME via/@ UPI"
    r"to\s+([a-zA-Z][a-zA-Z\s\.]+?)\s+(?:via|@)",
    # "to merchant NAME"
    r"to\s+(?:merchant|M/s\.?|Mr\.?|Mrs\.?|Ms\.?)\s*([a-zA-Z][a-zA-Z\s\.]+?)"
    + r"(?:\s+(?:via|@|on|for)\b|\s+(?:"
    + _NAME_STOP_WORDS
    + r")\b|\.|,|;|$)",
    # "Payment to NAME of Rs"
    r"Payment\s+to\s+([a-zA-Z][a-zA-Z\s\.]+?)\s+(?:of|for)\s+(?:Rs|INR|₹)",
    # "NAME - amount debited"
    r"([a-zA-Z][a-zA-Z\s\.]+?)\s*[-–]\s*(?:Rs|INR|₹)",
    # Additional patterns for common formats
    r"(?:Rs\.?|INR|₹)\s*[0-9,]+(?:\.[0-9]{2})?\s+(?:sent|paid|transferred)\s+to\s+"
    + r"([a-zA-Z][a-zA-Z\s\.]+?)"
    + _NAME_TERMINATOR,
    # Simple "to NAME" without via/UPI — the fallback every template reaches
    # when no verb precedes the payee. Matches lazily and shares
    # NAME_TERMINATOR so the stop words apply here too (a greedy,
    # stop-word-free version rendered "Big Merchant Has Failed").
    r"\bto\s+([a-zA-Z][a-zA-Z\s\.]{2,40}?)" + _NAME_TERMINATOR,
    # VPA format (name from UPI ID)
    r"to\s+([a-zA-Z][a-zA-Z0-9\s]+?)@",
    # Phone numbers - LAST PRIORITY
    r"to\s+(\d{10})(?:\s|\.|,|;|$)",
    # "<NAME> credited" — the payee position in dual-verb templates that name
    # both sides of one payment. Last, so every template that already
    # resolves keeps resolving exactly as before.
    r"\b([a-zA-Z][a-zA-Z\s\.]{2,40}?)\s+credited\b",
]

_SENDER_PATTERNS = [
    # "received from NAME"
    r"(?:received|credited)\s+from\s+([a-zA-Z][a-zA-Z\s\.]+?)(?:\s+(?:via|@|on|for)|\.|,|;|$)",
    # "from NAME via/@ UPI"
    r"from\s+([a-zA-Z][a-zA-Z\s\.]+?)\s+(?:via|@)",
    # Additional pattern for credit messages
    r"(?:Rs\.?|INR|₹)\s*[0-9,]+(?:\.[0-9]{2})?\s+(?:received|credited)\s+from\s+"
    + r"([a-zA-Z][a-zA-Z\s\.]+?)"
    + _NAME_TERMINATOR,
    # Simple "from NAME" — the credit-side twin of the bare "to NAME"
    # fallback, kept in step with it.
    r"\bfrom\s+([a-zA-Z][a-zA-Z\s\.]{2,40}?)" + _NAME_TERMINATOR,
    # Sender VPA
    r"from\s+([a-zA-Z][a-zA-Z0-9\s]+?)@",
]

# Bank identifiers - comprehensive list (insertion order matters: same as
# the Kotlin mapOf iteration order).
_BANK_KEYWORDS = {
    "HDFC": "HDFC Bank",
    "ICICI": "ICICI Bank",
    "SBI": "State Bank of India",
    "AXIS": "Axis Bank",
    "KOTAK": "Kotak Bank",
    "PNB": "Punjab National Bank",
    "BOB": "Bank of Baroda",
    "IDFC": "IDFC First Bank",
    "YES": "Yes Bank",
    "PAYTM": "Paytm Payments Bank",
    "UNION": "Union Bank",
    "CANARA": "Canara Bank",
    "IndusInd": "IndusInd Bank",
    "Federal": "Federal Bank",
}

# Transaction success indicators
_SUCCESS_INDICATORS = [
    "successful",
    "successfully",
    "completed",
    "credited",
    "debited",
    "transferred",
    "sent to",
    "received from",
    "payment of",
    "paid to",
    "txn successful",
]

# Failure indicators. Checked with absolute precedence: a bank SMS that
# matches the pipeline AND contains one of these is recorded as FAILED,
# never SUCCESS.
_FAILURE_INDICATORS = [
    "failed",
    "failure",
    "declined",
    "rejected",
    "unsuccessful",
    "not successful",
    "could not be processed",
    "cannot be processed",
    "not processed",
    "not completed",
    "insufficient",
    "reversed",
    "not debited",
    "txn expired",
    "timed out",
]

# Outgoing-payment verbs, checked before the credit words in
# detect_transaction_type. Many banks describe one payment from both sides
# in a single sentence, so a body carrying both verbs is ours only if the
# debit reading wins.
_DEBIT_INDICATORS = [
    "debited",
    "sent to",
    "paid to",
    "withdrawn",
    "spent",
    "transferred to",
]

# Verbs that mean money actually moved. Deliberately broader than
# _DEBIT_INDICATORS, which exists to decide *direction* — a real PNB
# template reads "Rs 3,499.00 transferred **from** PNB A/c ... to VPA
# merchant@okaxis", and gating on the direction list would discard it.
_TRANSACTION_VERBS = [
    "debited", "credited", "sent", "paid", "transferred",
    "withdrawn", "spent", "received", "deducted",
]

# Amount patterns - multiple formats
_AMOUNT_PATTERNS = [
    r"(?:Rs\.?|INR|₹)\s*([0-9,]+(?:\.[0-9]{1,2})?)",
    r"amount\s*(?:of)?\s*(?:Rs\.?|INR|₹)?\s*([0-9,]+(?:\.[0-9]{1,2})?)",
    r"([0-9,]+(?:\.[0-9]{1,2})?)\s*(?:Rs\.?|INR|₹)",
]

# Keywords that are also everyday English words. In the BODY these must
# appear as the full bank phrase — a promo like "Say YES to win Rs 5000!"
# must never be attributed to Yes Bank and enter the payment pipeline.
# Sender headers (VM-YESBNK, BOBTXN) still match by substring below.
_AMBIGUOUS_BODY_PHRASES = {
    "YES": re.compile(r"\bYES\s+BANK\b"),
    "BOB": re.compile(r"\bBANK\s+OF\s+BARODA\b|\bBOB\s+BANK\b"),
}

# Text immediately before a number that marks it as an account BALANCE,
# not the transaction amount.
_BALANCE_CONTEXT = re.compile(
    r"(?:avl|available|avlbl|a/c|account)?\s*bal(?:ance)?\s*[:.]?\s*$", re.IGNORECASE
)

# How far back to look for a balance marker before an amount match.
_BALANCE_LOOKBEHIND_CHARS = 24

_PAISE_PER_RUPEE = 100


def _default_clock() -> int:
    return int(time.time() * 1000)


def _default_random_suffix() -> int:
    return random.randint(1000, 9999)


def parse(
    sender: str,
    body: str,
    expected_amount: Optional[str],
    clock: Callable[[], int] = _default_clock,
    random_suffix: Callable[[], int] = _default_random_suffix,
) -> Optional[SimpleTransaction]:
    """Parse a candidate bank SMS into a SimpleTransaction, or None if it
    isn't a bank transaction message at all — no bank detected, no
    transaction-shaped body, or no amount found. Pure: no platform state."""
    bank_name = detect_bank(sender, body)
    if bank_name is None:
        return None
    if not is_transaction_message(body):
        return None
    amount = extract_amount(body)
    if amount is None:
        return None

    transaction_id = extract_transaction_id(body, clock) or generate_transaction_id(
        clock, random_suffix
    )
    upi_id = extract_upi_id(body)
    transaction_type = detect_transaction_type(body)
    recipient_name, phone_number = extract_recipient_info(body, transaction_type)

    # Everything below applies only to an outgoing payment we are waiting
    # on. Credits are never a debit's confirmation and are left to the
    # downstream path, which ignores them.
    if transaction_type != "CREDIT":
        # An amount alone is not a payment — see describes_transaction.
        if not describes_transaction(body):
            return None

        # A mismatched debit isn't our confirmation — return None so the
        # window stays open for the real one, instead of misattributing an
        # unrelated bank alert (an auto-debit, a card decline).
        if expected_amount and not is_amount_matching(amount, expected_amount):
            return None

    # Derive the outcome from the SMS itself: a failure keyword records
    # FAILED (banks send "Payment of Rs 500 failed"), otherwise SUCCESS.
    status = txn_status.FAILED if detects_failure(body) else txn_status.SUCCESS

    return SimpleTransaction(
        transaction_id=transaction_id,
        amount=amount,
        status=status,
        bank_name=bank_name,
        sms_excerpt=build_excerpt(amount, transaction_type, bank_name, status),
        timestamp=clock(),
        upi_id=upi_id,
        transaction_type=transaction_type,
        recipient_name=recipient_name,
        phone_number=phone_number,
    )


def describes_transaction(body: str) -> bool:
    """True when the body reports a transaction at all, as opposed to merely
    mentioning an amount. The gate that separates a payment message from
    everything else a bank or a marketer sends: balance alerts, promos and
    OTPs all carry an amount; none carry a verb."""
    body_lower = body.lower()
    return any(verb in body_lower for verb in _TRANSACTION_VERBS) or detects_failure(body)


def detects_failure(body: str) -> bool:
    """True when the SMS body reports a failed/declined transaction."""
    body_lower = body.lower()
    return any(ind in body_lower for ind in _FAILURE_INDICATORS)


def is_amount_matching(extracted: str, expected: str) -> bool:
    """Paise-exact comparison. "100" vs "100.00" still match (both are
    10000 paise), but 500 vs 500.75 is a mismatch."""
    try:
        extracted_num = float(extracted.replace(",", ""))
        expected_num = float(expected.replace(",", ""))
    except ValueError:
        return False
    # Math.round (half-up) semantics from the Kotlin original.
    return math.floor(extracted_num * _PAISE_PER_RUPEE + 0.5) == math.floor(
        expected_num * _PAISE_PER_RUPEE + 0.5
    )


def detect_bank(sender: str, body: str) -> Optional[str]:
    sender_upper = sender.upper()
    body_upper = body.upper()

    # Check sender first. DLT headers pack the bank into the code
    # (VK-HDFCBK, VM-YESBNK), so substring matching is correct here.
    for keyword, bank_name in _BANK_KEYWORDS.items():
        if keyword.upper() in sender_upper:
            return bank_name

    # Check body for bank names. Word-boundary matching, and the ambiguous
    # keywords ("YES", "BOB") additionally require the full bank phrase so
    # ordinary English can't smuggle a promo SMS in.
    for keyword, bank_name in _BANK_KEYWORDS.items():
        ambiguous = _AMBIGUOUS_BODY_PHRASES.get(keyword.upper())
        if ambiguous is not None:
            matched = ambiguous.search(body_upper) is not None
        else:
            matched = (
                re.search(r"\b" + re.escape(keyword.upper()) + r"\b", body_upper)
                is not None
            )
        if matched:
            return bank_name

    # Generic DLT-shaped sender fallback. Deliberately layered rather than
    # strict: downstream defenses (amount gate, failure keywords) keep a
    # promo sender non-catastrophic. The bare 6-letter and 6-digit forms
    # are kept ON PURPOSE: real banks use them (HDFCBK, SBIUPI, 561616).
    if (
        re.fullmatch(r"^[A-Z]{2}-[A-Z0-9]{6}(-[A-Z])?$", sender)
        or re.fullmatch(r"^[A-Z]{6}$", sender)
        or re.fullmatch(r"^[0-9]{6}$", sender)
    ):
        # It's likely a bank shortcode, but we don't know which one
        return "Bank"

    return None


def claim_key(body: str) -> str:
    """Dedupe key, built from the BODY only and deliberately not qualified
    by sender. Normalised (whitespace collapsed, capped at 120 chars) so
    cosmetically different deliveries of one message converge."""
    return re.sub(r"\s+", " ", body.strip())[:120]


def is_transaction_message(body: str) -> bool:
    body_lower = body.lower()

    for indicator in _SUCCESS_INDICATORS:
        if indicator in body_lower:
            return True

    # Failure SMS qualify too: "Payment declined" with no success verb must
    # still enter the pipeline so it can be recorded as FAILED.
    if detects_failure(body):
        return True

    for pattern in _AMOUNT_PATTERNS:
        if re.search(pattern, body, re.IGNORECASE):
            return True

    return False


def extract_amount(body: str) -> Optional[str]:
    """Collect every amount-shaped match across all patterns, in body
    order, then prefer the first that is NOT a balance figure. If every
    amount is a balance figure, fall back to it — the NEEDS_REVIEW
    mismatch tier is the safety net in the manual flow."""
    candidates = []
    for pattern in _AMOUNT_PATTERNS:
        for match in re.finditer(pattern, body, re.IGNORECASE):
            amount = match.group(1)
            if amount:
                candidates.append((match.start(), amount.replace(",", "")))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])

    non_balance = [
        c
        for c in candidates
        if not _BALANCE_CONTEXT.search(body[: c[0]][-_BALANCE_LOOKBEHIND_CHARS:])
    ]
    return (non_balance or candidates)[0][1]


def extract_transaction_id(body: str, clock: Callable[[], int]) -> Optional[str]:
    patterns = [
        # The \b are load-bearing. Without them "id" matched inside
        # "pa|id| to SHARMA STORE" and captured the following word, so a
        # receipt for the most common template read "Transaction ID
        # to_<timestamp>" instead of the bank's reference.
        r"\b(?:ref|txn|transaction|id)\b\s*(?:no|number|id)?\s*[:.#]?\s*([A-Z0-9]+)",
        r"([A-Z0-9]{10,})",  # generic pattern for long alphanumeric
    ]

    for pattern in patterns:
        match = re.search(pattern, body, re.IGNORECASE)
        if match is not None and match.lastindex and match.lastindex >= 1:
            base_id = match.group(1)
            if base_id:
                # Timestamp suffix keeps it unique even if a ref repeats.
                return f"{base_id}_{clock()}"

    return None


def extract_upi_id(body: str) -> Optional[str]:
    patterns = [
        r"(?:UPI:|from|to|UPI ID:?)\s*([a-zA-Z0-9._-]+@[a-zA-Z0-9]+)",
        r"(?:VPA:?)\s*([a-zA-Z0-9._-]+@[a-zA-Z0-9]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, body, re.IGNORECASE)
        if match is not None and match.lastindex and match.lastindex >= 1:
            return match.group(1)
    return None


def detect_transaction_type(body: str) -> str:
    """DEBIT (money left the user's account) or CREDIT (money arrived).

    A debit verb wins over a credit word: ICICI/Union-style templates name
    both sides of the same payment, and reading those as CREDIT would
    classify our own outgoing confirmation as somebody else's incoming
    money — the pipeline then drops it as unrelated and the payment never
    appears."""
    body_lower = body.lower()
    if any(ind in body_lower for ind in _DEBIT_INDICATORS):
        return "DEBIT"
    if "credited" in body_lower or "received" in body_lower or "added" in body_lower:
        return "CREDIT"
    return "DEBIT"


def generate_transaction_id(
    clock: Callable[[], int], random_suffix: Callable[[], int]
) -> str:
    return f"TXN{clock()}{random_suffix()}"


def extract_recipient_info(body: str, transaction_type: str):
    """Extract recipient (DEBIT) or sender (CREDIT) name and phone number.
    Returns (recipient_name, phone_number)."""
    recipient_name = None
    phone_number = None

    patterns = _SENDER_PATTERNS if transaction_type == "CREDIT" else _RECIPIENT_PATTERNS

    for pattern in patterns:
        match = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
        if match is None:
            continue
        extracted = (match.group(1) or "").strip()
        if not extracted:
            continue

        if re.fullmatch(r"\d{10}", extracted):
            phone_number = extracted
            continue

        cleaned_name = cleanup_name(extracted)
        if cleaned_name:
            recipient_name = cleaned_name
            break  # Stop if we found a good name

    # If no name found but we have a UPI ID, extract a name from it
    if not recipient_name:
        upi_name = extract_name_from_upi(body)
        if upi_name:
            recipient_name = upi_name

    return recipient_name, phone_number


def cleanup_name(name: str) -> Optional[str]:
    cleaned = name.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)  # multiple spaces to single space
    cleaned = re.sub(r"[\-–]$", "", cleaned)  # trailing dashes
    cleaned = re.sub(r"\.$", "", cleaned)  # trailing periods
    cleaned = cleaned.strip()

    # Remove common prefixes/suffixes that aren't part of the name
    for prefix in ("M/s", "Mr", "Mrs", "Ms", "Dr", "merchant", "Merchant"):
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix):].strip()
            if cleaned.startswith("."):
                cleaned = cleaned[1:].strip()

    # If name is too short or too long, it's probably not valid
    if len(cleaned) < 2 or len(cleaned) > 50:
        return None

    # If name contains no letters, it's not valid
    if not re.search(r"[a-zA-Z]", cleaned):
        return None

    # Convert to proper case (handle both uppercase and lowercase input)
    def _proper(word: str) -> str:
        lowered = word.lower()
        if not lowered:
            return lowered
        first = lowered[0]
        return (first.upper() if first.islower() else first) + lowered[1:]

    return " ".join(_proper(word) for word in cleaned.split(" "))


def extract_name_from_upi(body: str) -> Optional[str]:
    """e.g. 'johnsmith@okhdfcbank' -> 'John Smith', 'john.smith@ybl' -> 'John Smith'"""
    match = re.search(r"([a-zA-Z][a-zA-Z0-9._-]+)@[a-zA-Z0-9]+", body, re.IGNORECASE)
    if match is None:
        return None
    upi_prefix = match.group(1)
    if not upi_prefix:
        return None

    words = [
        word
        for word in upi_prefix.replace(".", " ").replace("_", " ").replace("-", " ").split(" ")
        if word
    ]
    return " ".join(word[:1].upper() + word[1:].lower() for word in words)


def build_excerpt(amount: str, transaction_type: str, bank_name: str, status: str) -> str:
    """Privacy-safe stored summary, built only from extracted fields so the
    raw SMS body (account fragments, balances) never reaches the database."""
    if status == txn_status.FAILED:
        verb = "payment failed"
    elif transaction_type == "CREDIT":
        verb = "credited"
    else:
        verb = "debited"
    excerpt = f"₹{amount} {verb}"
    if bank_name.strip():
        excerpt += f" — {bank_name}"
    return excerpt
