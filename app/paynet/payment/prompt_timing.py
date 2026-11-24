# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/payment/PaymentPromptTiming.kt

"""These delays pace guidance only; they never determine a payment outcome."""

CALLBACK_NOTICE_MS = 6_000
QR_ANSWER_DELAY_MS = 11_500


def remaining(started_at: int, delay_ms: int, now: int) -> int:
    return max(delay_ms - max(now - started_at, 0), 0)
