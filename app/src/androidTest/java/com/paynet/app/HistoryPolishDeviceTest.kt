// SPDX-License-Identifier: Apache-2.0
package com.paynet.app

import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import com.paynet.app.data.Transaction
import com.paynet.app.repository.TransactionRepository
import com.paynet.app.ui.activities.TransactionHistoryActivity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** Uses only synthetic records in the isolated test package. No payment is initiated. */
@RunWith(AndroidJUnit4::class)
class HistoryPolishDeviceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext
    private val device = UiDevice.getInstance(instrumentation)
    private val fixture = Transaction(
        "history-polish-qr", "", "USER_CONFIRMED", "Example bank", "",
        upiId = "polish-fixture@bank", recipientName = " ", bankRef = "POLISH-REF-987"
    )
    private val other = fixture.copy(
        transactionId = "history-polish-other", recipientName = "SECOND FIXTURE",
        upiId = "second-fixture@bank", bankRef = null, amount = "1"
    )

    @Before fun seedIsolatedRecords() {
        assertEquals("com.paynet.app.setupcheck", context.packageName)
        device.wakeUp()
        runBlocking(Dispatchers.IO) {
            TransactionRepository.getInstance(context).saveTransactions(listOf(fixture, other))
        }
    }

    @After fun removeOnlyFixtures() {
        if (context.packageName != "com.paynet.app.setupcheck") return
        runBlocking(Dispatchers.IO) {
            val repository = TransactionRepository.getInstance(context)
            repository.deleteTransactionById(fixture.transactionId)
            repository.deleteTransactionById(other.transactionId)
        }
    }

    @Test fun historySearchUsesUpiAndReferenceAndClosingRestoresRecords() {
        ActivityScenario.launch(TransactionHistoryActivity::class.java).use {
            it.onActivity { activity ->
                activity.window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
            assertTrue(device.wait(Until.hasObject(By.text("polish-fixture@bank")), 5000))
            device.findObject(By.res("history-search-toggle")).click()
            val search = device.wait(Until.findObject(By.clazz("android.widget.EditText")), 5000)
            search.text = "POLISH-REF-987"
            assertTrue(device.wait(Until.gone(By.text("Second Fixture")), 5000))
            assertTrue(device.hasObject(By.text("polish-fixture@bank")))
            assertFalse(device.hasObject(By.text("₹")))
            search.text = "polish-fixture@bank"
            assertTrue(device.wait(Until.hasObject(By.text("polish-fixture@bank")), 5000))
            device.findObject(By.res("history-search-toggle")).click()
            assertTrue(device.wait(Until.hasObject(By.text("Second Fixture")), 5000))
            assertFalse(device.hasObject(By.clazz("android.widget.EditText")))
        }
    }
}
