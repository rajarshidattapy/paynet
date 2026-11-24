# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/receivers/PaymentResultNotifier.kt

"""Posts a payment outcome as a high-priority notification.

The direct result-screen launch from a background receiver relies on the
background-activity-launch exemption granted by the overlay permission;
with that permission denied or revoked, the launch is silently dropped and
the user would never see their outcome. The notification is posted
ALONGSIDE the launch: tapping it opens the same result screen, and when
the direct launch did work it simply sits in the shade as a receipt.

Best-effort by design: on Android 13+ notifications additionally need the
POST_NOTIFICATIONS runtime grant; posting without it is a silent no-op,
never a crash.

DEVIATION: NotificationChannel/NotificationManager become an injected
`post` callable (plyer/pyjnius binding ships with the platform features and
is UNVERIFIED from desktop). The title/text mapping is pure and unit-tested;
titles are the strings.xml values.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from ..utils.currency import inr

log = logging.getLogger("PaymentResultNotifier")

CHANNEL_ID = "payment_results"
CHANNEL_NAME = "Payment results"
CHANNEL_DESCRIPTION = "The outcome of each payment — success, failure, or needs checking"

# strings.xml payment_status_* values, keyed by uppercased status.
_STATUS_TITLES = {
    "FAILED": "Payment Failed",
    "NEEDS_REVIEW": "Check This Payment",
    "UNVERIFIED": "No Confirmation Received",
}
_DEFAULT_TITLE = "Payment Successful"


def status_title(status: str) -> str:
    return _STATUS_TITLES.get(status.upper(), _DEFAULT_TITLE)


def notification_text(amount: str, bank: str) -> str:
    parts = [p for p in (f"₹{inr(amount)}", bank) if len(p) > 1]
    return " — ".join(parts)


def notify_result(result: dict, post: Optional[Callable[[int, str, str], None]] = None) -> None:
    """Post the outcome notification. `post` receives (notification_id,
    title, text); distinct id per payment so receipts don't overwrite each
    other. Failures are logged, never raised."""
    try:
        title = status_title(result.get("status") or "")
        text = notification_text(result.get("amount") or "", result.get("bank_name") or "")
        notification_id = hash(result.get("transaction_id") or "")
        if post is not None:
            post(notification_id, title, text)
    except (PermissionError, RuntimeError) as e:
        log.warning("Could not post payment result notification: %s", e)
