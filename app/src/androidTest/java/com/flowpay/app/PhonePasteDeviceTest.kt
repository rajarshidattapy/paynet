// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app

import android.app.Activity
import android.app.Application
import android.content.ClipData
import android.content.ClipboardManager
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.view.WindowManager
import android.view.accessibility.AccessibilityNodeInfo
import androidx.activity.compose.setContent
import androidx.compose.runtime.CompositionLocalProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.Until
import com.flowpay.app.ui.activities.TransactionHistoryActivity
import com.flowpay.app.ui.theme.BlueAccentTheme
import com.flowpay.app.ui.theme.FlowpayTheme
import com.flowpay.app.ui.theme.LocalFlowpayAccentTheme
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.atomic.AtomicReference

private const val PHONE_PASTE_TIMEOUT_MS = 5000L
private const val PHONE_PASTE_POLL_MS = 50L
private const val FIXTURE_PHONE = "9876543210"
private const val FIXTURE_CLIPBOARD_LABEL = "Phone fixture"

/** Real Android clipboard pastes into the isolated app; confirm is captured and never dials. */
@RunWith(AndroidJUnit4::class)
class PhonePasteDeviceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext
    private val application get() = context.applicationContext as Application
    private val device = UiDevice.getInstance(instrumentation)
    private var scenario: ActivityScenario<TransactionHistoryActivity>? = null
    private var originalClipboard: ClipData? = null
    private var clipboardCaptured = false
    private val confirmed = AtomicReference<Triple<String, String, String?>>()
    private val installedFixtures = mutableSetOf<Activity>()

    // Install at the same point for the initial Activity and recreation, before its first composition.
    private val fixtureLifecycle = object : Application.ActivityLifecycleCallbacks {
        override fun onActivityStarted(activity: Activity) {
            if (activity !is TransactionHistoryActivity || !installedFixtures.add(activity)) return
            activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            activity.setContent {
                CompositionLocalProvider(LocalFlowpayAccentTheme provides BlueAccentTheme) {
                    FlowpayTheme {
                        PayContactContent(
                            onDismiss = {},
                            onConfirm = { phone, amount, name -> confirmed.set(Triple(phone, amount, name)) }
                        )
                    }
                }
            }
        }

        override fun onActivityCreated(activity: Activity, state: Bundle?) = Unit
        override fun onActivityResumed(activity: Activity) = Unit
        override fun onActivityPaused(activity: Activity) = Unit
        override fun onActivityStopped(activity: Activity) = Unit
        override fun onActivitySaveInstanceState(activity: Activity, state: Bundle) = Unit
        override fun onActivityDestroyed(activity: Activity) { installedFixtures.remove(activity) }
    }

    @Before fun showIsolatedFixtureAndPreserveClipboard() {
        assertEquals("Refusing to run phone fixtures in production", "com.flowpay.app.setupcheck", context.packageName)
        device.wakeUp()
        application.registerActivityLifecycleCallbacks(fixtureLifecycle)
        scenario = ActivityScenario.launch(TransactionHistoryActivity::class.java)
        assertDialogVisible()
        // Android only allows clipboard reads to the focused app. Capture before changing it.
        requireNotNull(scenario).onActivity { activity ->
            originalClipboard = activity.getSystemService(ClipboardManager::class.java).primaryClip
            clipboardCaptured = true
        }
    }

    @After fun restoreClipboardBeforeClosingFixture() {
        try {
            if (clipboardCaptured) {
                scenario?.onActivity { activity ->
                    val clipboard = activity.getSystemService(ClipboardManager::class.java)
                    // A new copy made by the user during the fixture belongs to them; leave it intact.
                    if (clipboard.primaryClipDescription?.label?.toString() != FIXTURE_CLIPBOARD_LABEL) return@onActivity
                    val original = originalClipboard
                    if (original != null) {
                        clipboard.setPrimaryClip(original)
                    } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                        clipboard.clearPrimaryClip()
                    } else {
                        clipboard.setPrimaryClip(ClipData.newPlainText("", ""))
                    }
                }
            }
        } finally {
            scenario?.close()
            application.unregisterActivityLifecycleCallbacks(fixtureLifecycle)
            installedFixtures.clear()
        }
    }

    @Test fun actualClipboardPasteAcceptsIndianFormatsAndSubmitsOnlyTenDigits() {
        val formats = listOf(
            "domestic" to FIXTURE_PHONE,
            "country prefix and parentheses" to "+91 (98765) 43210",
            "bare country prefix" to "91-98765-43210",
            "trunk prefix" to "0 98765 43210",
            "copied line breaks" to "\n+91 98765\n43210\n"
        )
        for ((format, text) in formats) {
            clearPhone("before $format")
            paste(text)
            assertPhone(FIXTURE_PHONE, "after $format paste ${escaped(text)}")
        }
        device.findObjects(By.clazz("android.widget.EditText"))[1].text = "1"
        device.findObject(By.text(context.getString(R.string.action_transfer))).click()
        instrumentation.waitForIdleSync()
        assertEquals(Triple(FIXTURE_PHONE, "1", null), confirmed.get())
    }

    @Test fun actualClipboardPasteRejectsForeignNumbersTextAndUssd() {
        for (text in listOf("+44 9876543210", "1239876543210", "Call 9876543210", "*99#", "9876543210;1")) {
            clearPhone("before invalid paste ${escaped(text)}")
            paste(text)
            assertPhone("", "after invalid paste ${escaped(text)}")
            assertNull(confirmed.get())
        }
    }

    @Test fun pastedDraftCursorAndAmountSurviveRecreationAndMidTextEditingWorks() {
        paste("+91 98765 43210")
        assertPhone(FIXTURE_PHONE)
        device.findObjects(By.clazz("android.widget.EditText"))[1].text = "12"
        phoneField().click()
        selectPhone(4, 6)
        paste("00", focus = false)
        assertPhone("9876003210")
        assertEquals(6, phoneNode().textSelectionStart)
        requireNotNull(scenario).recreate()
        assertDialogVisible()
        assertPhone("9876003210")
        assertEquals("12", device.findObjects(By.clazz("android.widget.EditText"))[1].text)
        assertEquals("Recreation must retain the editing cursor", 6, phoneNode().textSelectionStart)
        phoneField().click()
        selectPhone(6, 6)
        device.pressDelete()
        assertPhone("987603210")
        assertNull("Editing the fixture must not initiate a payment", confirmed.get())
    }

    private fun assertDialogVisible() {
        assertTrue(device.wait(Until.hasObject(By.text(context.getString(R.string.pay_contact_title))), PHONE_PASTE_TIMEOUT_MS))
        device.waitForIdle()
    }

    private fun phoneField(): UiObject2 = requireNotNull(
        device.wait(Until.findObject(By.clazz("android.widget.EditText")), PHONE_PASTE_TIMEOUT_MS)
    )

    private fun assertPhone(expected: String, step: String = "phone edit") {
        val deadline = SystemClock.uptimeMillis() + PHONE_PASTE_TIMEOUT_MS
        var actual = phoneField().text
        while (actual != expected && SystemClock.uptimeMillis() < deadline) {
            SystemClock.sleep(PHONE_PASTE_POLL_MS)
            instrumentation.uiAutomation.clearCache()
            actual = device.findObject(By.clazz("android.widget.EditText"))?.text
        }
        if (actual != expected) {
            val node = phoneNode()
            assertEquals(
                "Expected ${escaped(expected)} $step; observed ${actual?.let(::escaped) ?: "<missing>"}, " +
                    "selection=${node.textSelectionStart}..${node.textSelectionEnd}",
                expected,
                actual
            )
        }
    }

    private fun clearPhone(step: String) {
        phoneField().text = ""
        // SetText and Paste are separate accessibility actions. Wait for the new
        // Compose value and selection before the next Paste reads its editor state.
        instrumentation.waitForIdleSync()
        device.waitForIdle()
        assertPhone("", step)
        // An empty editor has only offset zero. Samsung does not expose the
        // SetSelection accessibility action until there is text to select.
    }

    private fun paste(text: String, focus: Boolean = true) {
        if (focus) phoneField().click()
        requireNotNull(scenario).onActivity { activity ->
            val clipboard = activity.getSystemService(ClipboardManager::class.java)
            clipboard.setPrimaryClip(ClipData.newPlainText(FIXTURE_CLIPBOARD_LABEL, text))
            assertEquals("Fixture clipboard should contain the complete input", text, clipboard.primaryClip?.getItemAt(0)?.text?.toString())
        }
        assertTrue("Exercise Android's real Paste action", phoneNode().performAction(AccessibilityNodeInfo.ACTION_PASTE))
        instrumentation.waitForIdleSync()
        device.waitForIdle()
    }

    private fun escaped(text: String): String =
        "\"" + text.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + "\""

    private fun selectPhone(start: Int, end: Int) {
        val arguments = Bundle().apply {
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, start)
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, end)
        }
        assertTrue(phoneNode().performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, arguments))
        instrumentation.waitForIdleSync()
    }

    private fun phoneNode(): AccessibilityNodeInfo {
        instrumentation.uiAutomation.clearCache()
        return requireNotNull(findEditable(instrumentation.uiAutomation.rootInActiveWindow)) {
            "The focused payment dialog must expose its phone editor"
        }
    }

    private fun findEditable(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        if (node == null || node.isEditable) return node
        for (index in 0 until node.childCount) {
            findEditable(node.getChild(index))?.let { return it }
        }
        return null
    }
}
