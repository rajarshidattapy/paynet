# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from the formatDate helpers in MainActivity.kt /
# TransactionHistoryActivity.kt (SimpleDateFormat "dd MMM, HH:mm", en_IN).

import time


def format_date(timestamp_ms: int) -> str:
    return time.strftime("%d %b, %H:%M", time.localtime(timestamp_ms / 1000))


def format_time(timestamp_ms: int) -> str:
    # TransactionHistoryActivity.formatTime: SimpleDateFormat "hh:mm a".
    return time.strftime("%I:%M %p", time.localtime(timestamp_ms / 1000))


def format_full_date(timestamp_ms: int) -> str:
    # TransactionDetailDialog.formatFullDate: "dd MMM yyyy · h:mm a" (h is
    # unpadded, unlike the history row's "hh").
    t = time.localtime(timestamp_ms / 1000)
    return time.strftime("%d %b %Y · ", t) + time.strftime("%I:%M %p", t).lstrip("0")
