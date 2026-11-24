# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from the formatDate helpers in MainActivity.kt /
# TransactionHistoryActivity.kt (SimpleDateFormat "dd MMM, HH:mm", en_IN).

import time


def format_date(timestamp_ms: int) -> str:
    return time.strftime("%d %b, %H:%M", time.localtime(timestamp_ms / 1000))


def format_time(timestamp_ms: int) -> str:
    return time.strftime("%I:%M %p", time.localtime(timestamp_ms / 1000)).lstrip("0")
