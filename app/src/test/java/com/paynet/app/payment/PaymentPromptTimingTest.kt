// SPDX-License-Identifier: Apache-2.0
package com.paynet.app.payment
import org.junit.Assert.assertEquals
import org.junit.Test
private const val LATE_RESUME = 25000L
private const val QR_LAST_WAITING_INSTANT = 12499L
private const val QR_READY_INSTANT = 12500L
private const val CALLBACK_LAST_WAITING_INSTANT = 6999L
private const val CALLBACK_READY_INSTANT = 7000L
private const val CALLBACK_DURATION = 6000L
private const val QR_REMAINING_AFTER_FIVE_SECONDS = 6500L
private const val SAMPLE_DELAY = 5000L
private const val STARTED_AT = 1000L
private const val EARLIER_CLOCK = 900L

class PaymentPromptTimingTest {
    @Test fun callbackNoticeLastsSixSeconds() {
        assertEquals(
            CALLBACK_DURATION,
            PaymentPromptTiming.remaining(STARTED_AT, PaymentPromptTiming.CALLBACK_NOTICE_MS, STARTED_AT)
        )
        assertEquals(
            1L,
            PaymentPromptTiming.remaining(
                STARTED_AT,
                PaymentPromptTiming.CALLBACK_NOTICE_MS,
                CALLBACK_LAST_WAITING_INSTANT
            )
        )
        assertEquals(
            0L,
            PaymentPromptTiming.remaining(STARTED_AT, PaymentPromptTiming.CALLBACK_NOTICE_MS, CALLBACK_READY_INSTANT)
        )
    }

    @Test fun qrAnswersWaitElevenAndAHalfSecondsFromHandoff() {
        assertEquals(
            QR_REMAINING_AFTER_FIVE_SECONDS,
            PaymentPromptTiming.remaining(STARTED_AT, PaymentPromptTiming.QR_ANSWER_DELAY_MS, CALLBACK_DURATION)
        )
        assertEquals(
            1L,
            PaymentPromptTiming.remaining(STARTED_AT, PaymentPromptTiming.QR_ANSWER_DELAY_MS, QR_LAST_WAITING_INSTANT)
        )
        assertEquals(
            0L,
            PaymentPromptTiming.remaining(STARTED_AT, PaymentPromptTiming.QR_ANSWER_DELAY_MS, QR_READY_INSTANT)
        )
    }

    @Test fun lateResumeDoesNotRestartTheClock() {
        assertEquals(0L, PaymentPromptTiming.remaining(STARTED_AT, SAMPLE_DELAY, LATE_RESUME))
    }

    @Test fun invalidEarlierClockNeverShortensTheDelay() {
        assertEquals(SAMPLE_DELAY, PaymentPromptTiming.remaining(STARTED_AT, SAMPLE_DELAY, EARLIER_CLOCK))
    }
}
