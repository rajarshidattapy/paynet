// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.payment
import org.junit.Assert.assertEquals
import org.junit.Test
class PaymentPromptTimingTest {
    @Test fun callbackNoticeLastsSixSeconds() {
        assertEquals(6000L,PaymentPromptTiming.remaining(1000,PaymentPromptTiming.CALLBACK_NOTICE_MS,1000))
        assertEquals(1L,PaymentPromptTiming.remaining(1000,PaymentPromptTiming.CALLBACK_NOTICE_MS,6999))
        assertEquals(0L,PaymentPromptTiming.remaining(1000,PaymentPromptTiming.CALLBACK_NOTICE_MS,7000))
    }
    @Test fun qrAnswersWaitElevenAndAHalfSecondsFromHandoff() {
        assertEquals(6500L,PaymentPromptTiming.remaining(1000,PaymentPromptTiming.QR_ANSWER_DELAY_MS,6000))
        assertEquals(1L,PaymentPromptTiming.remaining(1000,PaymentPromptTiming.QR_ANSWER_DELAY_MS,12499))
        assertEquals(0L,PaymentPromptTiming.remaining(1000,PaymentPromptTiming.QR_ANSWER_DELAY_MS,12500))
    }
    @Test fun lateResumeDoesNotRestartTheClock() {
        assertEquals(0L,PaymentPromptTiming.remaining(1000,5000,25000))
    }
    @Test fun invalidEarlierClockNeverShortensTheDelay() {
        assertEquals(5000L,PaymentPromptTiming.remaining(1000,5000,900))
    }
}
