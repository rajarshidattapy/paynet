// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app

import android.graphics.BitmapFactory
import androidx.activity.compose.setContent
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import com.flowpay.app.data.Transaction
import com.flowpay.app.ui.activities.TransactionHistoryActivity
import com.flowpay.app.ui.components.TransactionDetailDialog
import com.flowpay.app.ui.theme.*
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.concurrent.atomic.AtomicInteger

/** Isolated, in-memory receipts. No payment, database mutation or deletion is performed. */
@RunWith(AndroidJUnit4::class)
class TransactionDetailDeviceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext
    private val device = UiDevice.getInstance(instrumentation)
    private val fixture = Transaction(
        "receipt-design-fixture", "", "USER_CONFIRMED", "Hidden bank", "", 1793688720000L,
        recipientName = "SAMPLE MERCHANT", upiId = "merchant@upi"
    )

    @Before fun isolatedOnly() {
        assertEquals("Refusing to run receipt fixtures in production", "com.flowpay.app.setupcheck", context.packageName)
        device.wakeUp()
    }

    private fun show(
        row: Transaction = fixture,
        blue: Boolean = false,
        fontScale: Float = 1f,
        onDismiss: () -> Unit = {},
        onDelete: (() -> Unit)? = null
    ): ActivityScenario<TransactionHistoryActivity> {
        val scenario = ActivityScenario.launch(TransactionHistoryActivity::class.java)
        scenario.onActivity { activity ->
            activity.window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            activity.setContent {
                val density = LocalDensity.current
                CompositionLocalProvider(
                    LocalFlowpayAccentTheme provides if (blue) BlueAccentTheme else MonochromeAccentTheme,
                    LocalDensity provides Density(density.density, fontScale)
                ) {
                    FlowpayTheme { TransactionDetailDialog(row, onDismiss, onDelete) }
                }
            }
        }
        assertTrue(device.wait(Until.hasObject(By.res("transaction-detail-dialog")), 5000))
        return scenario
    }

    private fun revealDone() {
        repeat(8) {
            val done = device.findObject(By.res("transaction-detail-done"))
            if (done != null && done.visibleBounds.height() > 30) return
            device.swipe(360, 1320, 360, 650, 30)
        }
    }

    private fun screenshot(name: String) {
        device.takeScreenshot(File(context.getExternalFilesDir(null), "$name.png"))
    }


    private fun assertActionColor(tag: String, expected: Color, screenshotName: String) {
        device.waitForIdle()
        val bounds = device.findObject(By.res(tag)).visibleBounds
        val file = File(context.getExternalFilesDir(null), "$screenshotName.png")
        assertTrue(device.takeScreenshot(file))
        val bitmap = BitmapFactory.decodeFile(file.path)
        try {
            // Sample inside the filled action, clear of its rounded edge and centered label.
            val pixel = bitmap.getPixel(bounds.left + bounds.width() / 10, bounds.centerY())
            val target = expected.toArgb()
            for (shift in listOf(0, 8, 16)) {
                assertTrue("Action $tag must use the selected theme", kotlin.math.abs(
                    ((pixel shr shift) and 255) - ((target shr shift) and 255)
                ) <= 2)
            }
        } finally { bitmap.recycle() }
    }

    @Test fun receiptActionsFollowBothSelectedThemes() {
        for (blue in listOf(false, true)) {
            show(blue = blue).use {
                revealDone()
                val theme = if (blue) BlueAccentTheme else MonochromeAccentTheme
                assertActionColor("transaction-detail-done", theme.primaryDark,
                    if (blue) "receipt-selected-blue" else "receipt-selected-monochrome")
            }
        }
    }

    @Test fun blankAmountHasNoCurrencyAndDoneDismisses() {
        val dismissals = AtomicInteger()
        show(onDismiss = { dismissals.incrementAndGet() }).use {
            assertTrue(device.hasObject(By.text("Sample Merchant")))
            assertFalse(device.hasObject(By.text(context.getString(R.string.home_confirmed))))
            assertFalse(device.hasObject(By.text(context.getString(R.string.detail_status))))
            assertFalse(device.hasObject(By.text(context.getString(R.string.detail_user_reported))))
            assertFalse(device.hasObject(By.text("Hidden bank")))
            assertFalse(device.hasObject(By.text("₹")))
            assertFalse(device.hasObject(By.text(context.getString(R.string.detail_amount))))
            screenshot("receipt-monochrome")
            revealDone()
            device.findObject(By.res("transaction-detail-done")).click()
            assertEquals(1, dismissals.get())
        }
    }

    @Test fun recordedAmountAndReferenceRemainCopyable() {
        show(fixture.copy(amount = "123456.78", status = "UNVERIFIED", bankRef = "REFERENCE-123"), blue = true).use { scenario ->
            var previousClip: android.content.ClipData? = null
            scenario.onActivity { previousClip = it.getSystemService(android.content.ClipboardManager::class.java).primaryClip }
            try {
                assertTrue(device.hasObject(By.text("₹1,23,456.78")))
                device.swipe(360, 1300, 360, 900, 20)
                assertTrue(device.wait(Until.hasObject(By.text("REFERENCE-123")),5000))
                val label = context.getString(R.string.detail_copy_field, context.getString(R.string.label_upi_id))
                device.findObject(By.desc(label)).click()
                scenario.onActivity {
                    val clipboard = it.getSystemService(android.content.ClipboardManager::class.java)
                    assertEquals("merchant@upi", clipboard.primaryClip!!.getItemAt(0).text.toString())
                }
                screenshot("receipt-blue")
            } finally {
                scenario.onActivity {
                    val clipboard = it.getSystemService(android.content.ClipboardManager::class.java)
                    if (clipboard.primaryClip?.getItemAt(0)?.text?.toString() == "merchant@upi") {
                        previousClip?.let(clipboard::setPrimaryClip) ?: clipboard.clearPrimaryClip()
                    }
                }
            }
        }
    }

    @Test fun deletingCanBeCancelledWithoutDeletingTheRecord() {
        val deletions = AtomicInteger()
        show(onDelete = { deletions.incrementAndGet() }).use {
            repeat(6) {
                instrumentation.uiAutomation.clearCache()
                val button = device.findObject(By.res("transaction-detail-delete"))
                if (button == null || button.visibleBounds.height() < 70) {
                    device.swipe(360, 1260, 360, 900, 20)
                    device.waitForIdle()
                }
            }
            instrumentation.uiAutomation.clearCache()
            device.findObject(By.res("transaction-detail-delete")).click()
            assertTrue(device.wait(Until.hasObject(By.res("transaction-delete-dialog")), 5000))
            assertActionColor("transaction-delete-cancel", MonochromeAccentTheme.primaryDark, "receipt-delete-confirmation")
            device.findObject(By.text(context.getString(R.string.action_cancel))).click()
            assertTrue(device.wait(Until.hasObject(By.res("transaction-detail-dialog")), 5000))
            assertEquals(0, deletions.get())
        }
    }

    @Test fun largeTextAndLongIdentifiersCanScrollToActions() {
        val dismissals = AtomicInteger()
        show(
            fixture.copy(recipientName = "A VERY LONG MERCHANT NAME WITH MULTIPLE WORDS", upiId = "long.merchant.identifier.with.many.parts@bank"),
            fontScale = 1.6f,
            onDismiss = { dismissals.incrementAndGet() }
        ).use {
            screenshot("receipt-large-text-top")
            repeat(6) {
                val done = device.findObject(By.res("transaction-detail-done"))
                if (done != null && done.visibleBounds.height() > 20) return@repeat
                device.swipe(360, 1230, 360, 550, 30)
            }
            screenshot("receipt-large-text-bottom")
            device.findObject(By.res("transaction-detail-done")).click()
            assertEquals(1, dismissals.get())
        }
    }
}
