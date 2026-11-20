// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.payment

/** These delays pace guidance only; they never determine a payment outcome. */
object PaymentPromptTiming {
    const val CALLBACK_NOTICE_MS = 6000L
    const val QR_ANSWER_DELAY_MS = 11500L
    fun remaining(startedAt: Long, delayMs: Long, now: Long): Long =
        (delayMs - (now - startedAt).coerceAtLeast(0L)).coerceAtLeast(0L)
}
