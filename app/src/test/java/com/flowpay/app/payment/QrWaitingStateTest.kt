// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.payment

import com.flowpay.app.states.PaymentState
import com.flowpay.app.states.TimeoutType
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class QrWaitingStateTest {
    @Test fun deadlineClosesOnlyTheOwningScreen() {
        val state = PaymentState.Timeout(TimeoutType.BANK_VERIFICATION, "", "500", "qr")
        assertTrue(shouldCloseQrWaitingScreen("qr", state))
        assertFalse(shouldCloseQrWaitingScreen("other", state))
        assertFalse(shouldCloseQrWaitingScreen(null, state))
    }

    @Test fun pendingConfirmationKeepsTheScreenOpen() {
        val state = PaymentState.WaitingForVerification(0L, "", "500", "qr")
        assertFalse(shouldCloseQrWaitingScreen("qr", state))
    }

    @Test fun confirmedResultClosesItsScreen() {
        val state = PaymentState.Success("qr", "", "500", "ref", 1L)
        assertTrue(shouldCloseQrWaitingScreen("qr", state))
        assertFalse(shouldCloseQrWaitingScreen("other", state))
    }
}
