// SPDX-License-Identifier: Apache-2.0
package com.paynet.app

import android.content.res.Configuration
import android.os.SystemClock
import android.view.ContextThemeWrapper
import android.view.accessibility.AccessibilityWindowInfo
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.ViewCompositionStrategy
import androidx.compose.ui.unit.Density
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.BySelector
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.Until
import com.paynet.app.ui.activities.SettingsScreen
import com.paynet.app.ui.activities.SettingsViewModel
import com.paynet.app.ui.activities.TransactionHistoryActivity
import com.paynet.app.ui.dialogs.ContactPickerDialog
import com.paynet.app.ui.theme.BlueAccentTheme
import com.paynet.app.ui.theme.PayNetTheme
import com.paynet.app.ui.theme.LocalPayNetAccentTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.concurrent.atomic.AtomicInteger

private const val UI_TIMEOUT_MS = 5000L
private const val POLL_DELAY_MS = 50L
private const val LARGE_FONT_SCALE = 1.6f
private const val MIN_FONT_GROWTH = 1.2f
private const val MAX_SCROLLS = 10
private const val SWIPE_STEPS = 30
private const val SCROLL_START = 0.80f
private const val SCROLL_END = 0.35f
private const val MIN_TARGET_HEIGHT_DP = 48
private const val TARGET_EDGE_MARGIN_DP = 8
private const val CLOSED_FIXTURE = "Fixture closed"

/** Isolated rendering only: no payment callback, permission grant or settings mutation is performed. */
@RunWith(AndroidJUnit4::class)
class PolishUiDeviceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext
    private val device = UiDevice.getInstance(instrumentation)

    @Before fun isolatedOnly() {
        assertEquals("Refusing to run UI fixtures in production", "com.paynet.app.setupcheck", context.packageName)
        device.wakeUp()
    }

    private fun show(
        fontScale: Float = 1f,
        content: @Composable () -> Unit
    ): ActivityScenario<TransactionHistoryActivity> {
        val scenario = ActivityScenario.launch(TransactionHistoryActivity::class.java)
        scenario.onActivity { activity ->
            activity.window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            // Give dialog windows the same local font configuration; never change Android's font setting.
            val themedContext = ContextThemeWrapper(activity, R.style.Theme_PayNet).apply {
                applyOverrideConfiguration(Configuration(activity.resources.configuration).apply { this.fontScale = fontScale })
            }
            val composeView = ComposeView(themedContext).apply {
                setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnViewTreeLifecycleDestroyed)
                setContent {
                    CompositionLocalProvider(
                        LocalPayNetAccentTheme provides BlueAccentTheme,
                        LocalDensity provides Density(activity.resources.displayMetrics.density, fontScale)
                    ) {
                        PayNetTheme { content() }
                    }
                }
            }
            activity.setContentView(composeView)
        }
        return scenario
    }

    private fun visible(selector: BySelector): UiObject2 {
        val found = device.wait(Until.hasObject(selector), UI_TIMEOUT_MS)
        if (!found) device.takeScreenshot(File(context.getExternalFilesDir(null), "polish-missing-control.png"))
        assertTrue("Expected visible control: $selector", found)
        return requireNotNull(device.findObject(selector)).also {
            assertTrue("Control must have a visible target", it.visibleBounds.height() > 0 && it.visibleBounds.width() > 0)
        }
    }

    private fun reveal(selector: BySelector): UiObject2 {
        repeat(MAX_SCROLLS) {
            device.waitForIdle()
            instrumentation.uiAutomation.clearCache()
            device.findObject(selector)?.let { target ->
                if (safelyRevealed(target)) return target
            }
            device.swipe(
                device.displayWidth / 2, (device.displayHeight * SCROLL_START).toInt(),
                device.displayWidth / 2, (device.displayHeight * SCROLL_END).toInt(), SWIPE_STEPS
            )
        }
        return visible(selector).also {
            assertTrue("The complete click target must be reachable within settings", safelyRevealed(it))
        }
    }

    private fun safelyRevealed(target: UiObject2): Boolean {
        val bounds = target.visibleBounds
        val density = context.resources.displayMetrics.density
        val viewport = device.findObject(By.res("settings-content"))?.visibleBounds ?: return false
        val margin = (TARGET_EDGE_MARGIN_DP * density).toInt()
        return bounds.height() >= MIN_TARGET_HEIGHT_DP * density && bounds.width() > 0 &&
            bounds.top >= viewport.top + margin && bounds.bottom <= viewport.bottom - margin
    }

    private fun screenshot(name: String) {
        assertTrue(device.takeScreenshot(File(context.getExternalFilesDir(null), "$name.png")))
    }

    private fun assertKeyboardVisible() {
        val deadline = SystemClock.uptimeMillis() + UI_TIMEOUT_MS
        while (SystemClock.uptimeMillis() < deadline) {
            if (instrumentation.uiAutomation.windows.any { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD }) return
            SystemClock.sleep(POLL_DELAY_MS)
        }
        assertTrue("The keyboard should be open for this layout check", false)
    }

    @Test fun settingsRemainReadableAndResetCanBeCancelledAtBothTextSizes() {
        var normalHeadingHeight = 0
        val permissionRequests = AtomicInteger()
        for (fontScale in listOf(1f, LARGE_FONT_SCALE)) {
            show(fontScale) {
                val model = remember { SettingsViewModel() }
                SettingsScreen(
                    viewModel = model,
                    onBackPressed = {},
                    onRequestPermissions = { permissionRequests.incrementAndGet() }
                )
            }.use {
                val heading = visible(By.text(context.getString(R.string.settings_refined_appearance)))
                visible(By.text(context.getString(R.string.home_color)))
                if (fontScale == 1f) {
                    normalHeadingHeight = heading.visibleBounds.height()
                    screenshot("polish-settings-blue")
                } else {
                    assertTrue("The fixture must actually render larger text", heading.visibleBounds.height() > normalHeadingHeight * MIN_FONT_GROWTH)
                    screenshot("polish-settings-large")
                }
                reveal(By.res("settings-clear-app-data")).click()
                device.waitForIdle()
                screenshot(if (fontScale == 1f) "polish-settings-reset-normal" else "polish-settings-reset-large")
                visible(By.text(context.getString(R.string.settings_reset_title)))
                visible(By.text(context.getString(R.string.action_cancel))).click()
                assertTrue(device.wait(Until.gone(By.text(context.getString(R.string.settings_reset_title))), UI_TIMEOUT_MS))
                visible(By.text(context.getString(R.string.settings_clear_data_title)))
            }
        }
        assertEquals("Checking settings must not request phone permissions", 0, permissionRequests.get())
    }

    @Test fun payContactLargeTextKeepsCancelReachableWithTheKeyboardOpen() {
        val confirmations = AtomicInteger()
        val dismissals = AtomicInteger()
        show(LARGE_FONT_SCALE) {
            var open by remember { mutableStateOf(true) }
            if (open) {
                PayContactDialog(
                    onDismiss = { dismissals.incrementAndGet(); open = false },
                    onConfirm = { _, _, _ -> confirmations.incrementAndGet() }
                )
            } else {
                Text(CLOSED_FIXTURE)
            }
        }.use {
            visible(By.text(context.getString(R.string.pay_contact_title)))
            val mobile = visible(By.clazz("android.widget.EditText"))
            mobile.click()
            mobile.text = "9876543210"
            assertKeyboardVisible()
            screenshot("polish-pay-contact-keyboard-large")
            visible(By.text(context.getString(R.string.action_cancel))).click()
            visible(By.text(CLOSED_FIXTURE))
            assertEquals(1, dismissals.get())
            assertEquals("The fixture must never initiate a payment", 0, confirmations.get())
        }
    }

    @Test fun contactPickerLargeTextKeepsSearchAndCloseReachableWithKeyboard() {
        val selections = AtomicInteger()
        val dismissals = AtomicInteger()
        show(LARGE_FONT_SCALE) {
            var open by remember { mutableStateOf(true) }
            if (open) {
                ContactPickerDialog(
                    onDismiss = { dismissals.incrementAndGet(); open = false },
                    onContactSelected = { selections.incrementAndGet() }
                )
            } else {
                Text(CLOSED_FIXTURE)
            }
        }.use {
            visible(By.text(context.getString(R.string.polish_contacts_title)))
            val search = visible(By.clazz("android.widget.EditText"))
            search.click()
            search.text = "paynet-fixture-no-match"
            assertKeyboardVisible()
            screenshot("polish-contact-large")
            visible(By.desc(context.getString(R.string.polish_contacts_close))).click()
            visible(By.text(CLOSED_FIXTURE))
            assertEquals(1, dismissals.get())
            assertEquals("Searching must never select a recipient", 0, selections.get())
        }
    }
}
