# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/test/java/com/paynet/app/payment/PaymentPromptTimingTest.kt

from paynet.payment.prompt_timing import (
    CALLBACK_NOTICE_MS,
    QR_ANSWER_DELAY_MS,
    remaining,
)

STARTED_AT = 1000


def test_callback_notice_lasts_six_seconds():
    assert remaining(STARTED_AT, CALLBACK_NOTICE_MS, STARTED_AT) == 6000
    assert remaining(STARTED_AT, CALLBACK_NOTICE_MS, 6999) == 1
    assert remaining(STARTED_AT, CALLBACK_NOTICE_MS, 7000) == 0


def test_qr_answers_wait_eleven_and_a_half_seconds_from_handoff():
    assert remaining(STARTED_AT, QR_ANSWER_DELAY_MS, 6000) == 6500
    assert remaining(STARTED_AT, QR_ANSWER_DELAY_MS, 12499) == 1
    assert remaining(STARTED_AT, QR_ANSWER_DELAY_MS, 12500) == 0


def test_late_resume_does_not_restart_the_clock():
    assert remaining(STARTED_AT, 5000, 25000) == 0


def test_invalid_earlier_clock_never_shortens_the_delay():
    assert remaining(STARTED_AT, 5000, 900) == 5000
