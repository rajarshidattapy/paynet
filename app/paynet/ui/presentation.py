# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/ui/activities/TransactionPresentation.kt

"""Transaction presentation helpers shared by history/home surfaces."""

import time

from paynet.db.models import Transaction


def matches_search(transaction: Transaction, query: str) -> bool:
    text = query.strip()
    if not text:
        return True
    text_lower = text.lower()
    return any(
        value is not None and text_lower in value.lower()
        for value in (
            transaction.recipientName,
            transaction.recipient_label,
            transaction.phoneNumber,
            transaction.upiId,
            transaction.bankRef,
            transaction.bankName,
            transaction.amount,
        )
    )


def historical_date_label(timestamp: int, now: int) -> str:
    """Include the year for older records, keeping dates from different
    years distinct. Timestamps are epoch milliseconds."""
    current = time.localtime(now / 1000)
    date = time.localtime(timestamp / 1000)
    if date.tm_year == current.tm_year:
        return time.strftime("%d %b", date)
    return time.strftime("%d %b %Y", date)
