// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app

import android.content.Intent
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.lifecycle.Lifecycle
import com.flowpay.app.features.qr_scanner.presentation.QRScannerActivity
import com.flowpay.app.helpers.TransactionDetector
import com.flowpay.app.states.PaymentState
import com.flowpay.app.states.TimeoutType
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Exercises the real screen collector without dialing or creating payment records. */
@RunWith(AndroidJUnit4::class)
class QrTimeoutDeviceTest {
    @Test fun deadlineClosesScannerButPreservesLateMessageWindow() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val manager = FlowpayApplication.from(context)!!.paymentSessionManager
        val stateField = manager.javaClass.getDeclaredField("_paymentState").apply { isAccessible = true }
        @Suppress("UNCHECKED_CAST")
        val states = stateField.get(manager) as MutableStateFlow<PaymentState>
        val previous = states.value
        val detector = TransactionDetector.getInstance(context)
        val id = "synthetic-qr-timeout"
        val scenario = ActivityScenario.launch<QRScannerActivity>(Intent(context, QRScannerActivity::class.java))
        try {
            scenario.onActivity { activity ->
                activity.javaClass.getDeclaredField("qrTransactionId").apply { isAccessible = true }.set(activity, id)
                states.value = PaymentState.WaitingForVerification(0L, "", "500", id)
            }
            Thread.sleep(150)
            assertEquals(Lifecycle.State.RESUMED, scenario.state)
            detector.startOperation("QR_SCAN", "500", sessionTxnId = id)
            states.value = PaymentState.Timeout(TimeoutType.BANK_VERIFICATION, "", "500", id)
            val deadline = android.os.SystemClock.uptimeMillis() + 5000
            while (scenario.state != Lifecycle.State.DESTROYED && android.os.SystemClock.uptimeMillis() < deadline) {
                Thread.sleep(50)
            }
            assertEquals(Lifecycle.State.DESTROYED, scenario.state)
            assertTrue(detector.shouldProcessSMS())
            assertTrue(states.value is PaymentState.Timeout)
        } finally {
            scenario.close()
            detector.stopOperation()
            states.value = previous
        }
    }
}
