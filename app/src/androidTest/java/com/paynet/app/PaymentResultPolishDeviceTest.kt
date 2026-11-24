// SPDX-License-Identifier: Apache-2.0
package com.paynet.app

import android.content.Intent
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import com.paynet.app.ui.activities.PaymentResultActivity
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class PaymentResultPolishDeviceTest {
    @Test fun resultStatesRemainReadableAndKeepTheirLayout() {
        val instrument = InstrumentationRegistry.getInstrumentation()
        val context = instrument.targetContext
        val device = UiDevice.getInstance(instrument)
        for (status in listOf("SUCCESS", "FAILED", "UNVERIFIED")) {
            val intent = Intent(context, PaymentResultActivity::class.java).apply {
                putExtra("status", status)
                putExtra("amount", "250.00")
                putExtra("recipient_name", "Demo merchant")
                putExtra("bank_name", "Test bank")
                putExtra("transaction_id", "DEMO123456_1000")
                putExtra("timestamp", 1793780000000L)
            }
            ActivityScenario.launch<PaymentResultActivity>(intent).use { scenario ->
                assertTrue(device.wait(Until.hasObject(By.res(context.packageName,"btn_done")),5000))
                device.waitForIdle()
                var visible = false
                val deadline = android.os.SystemClock.uptimeMillis() + 5000
                while (!visible && android.os.SystemClock.uptimeMillis() < deadline) {
                    scenario.onActivity { activity ->
                        visible = listOf(R.id.tv_amount, R.id.card_details, R.id.btn_done).all { id ->
                            activity.findViewById<android.view.View>(id).alpha >= .99f
                        }
                    }
                    if (!visible) Thread.sleep(50)
                }
                assertTrue("Result content must become visible", visible)
                device.waitForIdle()
                val heading = device.findObject(By.res(context.packageName,"tv_status"))
                assertNotNull(heading)
                assertNotNull(device.findObject(By.text("Demo merchant")))
                assertTrue(device.findObject(By.res(context.packageName,"btn_done")).isEnabled)
                if (status != "SUCCESS") assertFalse(heading.text.contains("successful",ignoreCase=true))
                assertTrue(device.takeScreenshot(File(context.getExternalFilesDir(null),"result-$status.png")))
            }
        }
    }
}
