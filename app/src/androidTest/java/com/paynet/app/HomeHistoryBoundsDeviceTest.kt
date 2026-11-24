// SPDX-License-Identifier: Apache-2.0
package com.paynet.app

import android.graphics.Rect
import android.view.WindowManager
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.BySelector
import androidx.test.uiautomator.Direction
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.Until
import com.paynet.app.data.PaymentDetails
import com.paynet.app.data.PaymentStatus
import com.paynet.app.ui.activities.TransactionHistoryActivity
import com.paynet.app.ui.home.HomeAppearance
import com.paynet.app.ui.home.HomeDashboard
import com.paynet.app.ui.theme.PayNetTheme
import com.paynet.app.ui.theme.LocalPayNetAccentTheme
import com.paynet.app.ui.theme.accentThemeFor
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.concurrent.atomic.AtomicInteger
import java.util.regex.Pattern

/** Real layout, synthetic in-memory records and inert callbacks; never opens a payment or changes OS settings. */
@RunWith(AndroidJUnit4::class)
class HomeHistoryBoundsDeviceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext
    private val device = UiDevice.getInstance(instrumentation)
    private val preferences = context.getSharedPreferences("PayNetPrefs", android.content.Context.MODE_PRIVATE)
    private val payments = mutableStateOf<List<PaymentDetails>>(emptyList())
    private val scans = AtomicInteger()
    private val contacts = AtomicInteger()
    private val historyOpens = AtomicInteger()
    private val transactionOpens = AtomicInteger()
    private var savedAppearance: Map<String, Boolean?>? = null

    @Before fun isolateFixture() {
        assertEquals("Refusing to run fixtures in production", "com.paynet.app.setupcheck", context.packageName)
        savedAppearance = listOf("home_classic", "home_monochrome").associateWith {
            if (preferences.contains(it)) preferences.getBoolean(it, false) else null
        }
        device.wakeUp()
    }

    @After fun restoreAppearance() {
        val saved = savedAppearance ?: return
        preferences.edit().apply {
            saved.forEach { (key, value) -> if (value == null) remove(key) else putBoolean(key, value) }
        }.commit()
    }

    @Test fun modernHistoryAndQrKeepEmptyBoundsWithTenAndThirtyRecords() {
        for (monochrome in listOf(true, false)) {
            show(HomeAppearance(monochrome = monochrome)).use {
                val empty = geometry(withScan = true)
                val expectedBottomInset = QR_BOTTOM_DP * context.resources.displayMetrics.density
                assertTrue("The empty-state QR anchor must preserve its anchor while the card extends 32dp below it",
                    kotlin.math.abs(empty.panel.bottom - requireNotNull(empty.scan).bottom - expectedBottomInset) <= 1f)
                screenshot("modern-${if (monochrome) "mono" else "blue"}-empty")
                for (count in listOf(TEN_RECORDS, THIRTY_RECORDS)) {
                    updateRecords(count)
                    assertEquals("Adding records must not grow the card or move its QR", empty, geometry(withScan = true))
                    assertListExtendsBehindScan()
                    scrollInsideHistory(count, empty, withScan = true)
                    assertListExtendsBehindScan()
                    screenshot("modern-${if (monochrome) "mono" else "blue"}-$count")
                    assertActionsReachable()
                    if (count == TEN_RECORDS) {
                        assertLastRowCanClearScan(count)
                        assertEquals("End-of-list overscroll must stay inside the card", empty, geometry(withScan = true))
                    }
                }
            }
        }
        assertEquals(0, transactionOpens.get())
    }

    @Test fun classicMonochromeHistoryScrollsInsideItsOriginalBox() {
        show(HomeAppearance(classic = true, monochrome = true)).use {
            revealWholeClassicCard()
            val empty = geometry(withScan = false)
            for (count in listOf(TEN_RECORDS, THIRTY_RECORDS)) {
                updateRecords(count)
                assertEquals("Classic history must keep its empty-state box", empty, geometry(withScan = false))
                scrollInsideHistory(count, empty, withScan = false)
                screenshot("classic-mono-$count")
                visible(By.text(context.getString(R.string.home_view_all))).click()
            }
        }
        assertEquals(2, historyOpens.get())
        assertEquals(0, transactionOpens.get())
        assertEquals(0, scans.get())
        assertEquals(0, contacts.get())
    }

    private fun show(appearance: HomeAppearance): ActivityScenario<TransactionHistoryActivity> {
        appearance.save(context)
        instrumentation.runOnMainSync { payments.value = emptyList() }
        return ActivityScenario.launch(TransactionHistoryActivity::class.java).also { scenario ->
            scenario.onActivity { activity ->
                activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                activity.setContent {
                    CompositionLocalProvider(LocalPayNetAccentTheme provides accentThemeFor(appearance)) {
                        PayNetTheme {
                            Box(Modifier.fillMaxSize().semantics { testTagsAsResourceId = true }) {
                                HomeDashboard(
                                    selectedBankName = "State Bank of India",
                                    recentPayments = payments.value,
                                    isLoading = false,
                                    error = null,
                                    onRetry = {},
                                    onTransaction = { transactionOpens.incrementAndGet() },
                                    onSettings = {},
                                    onHistory = { historyOpens.incrementAndGet() },
                                    onQRScanClick = { scans.incrementAndGet() },
                                    onPayContactClick = { contacts.incrementAndGet() },
                                    isUpi123Ready = true,
                                    isUssdReady = true,
                                    isScanning = false
                                )
                            }
                        }
                    }
                }
            }
            visible(By.desc(context.getString(R.string.home_settings)))
        }
    }

    private fun updateRecords(count: Int) {
        instrumentation.runOnMainSync {
            payments.value = List(count) { index ->
                PaymentDetails(
                    id = "home-fixture-$count-$index",
                    recipientName = label(count, index),
                    phoneNumber = "9876543210",
                    amount = 1.0,
                    timestamp = FIXTURE_TIMESTAMP - index * DAY_MS,
                    status = PaymentStatus.UNVERIFIED,
                    userConfirmed = true
                )
            }
        }
        visible(recipientSelector(count))
        settle()
    }

    private data class HeadingPosition(val left: Int, val top: Int, val right: Int)

    private data class Geometry(val panel: Rect, val header: HeadingPosition, val scan: Rect?)

    private fun geometry(withScan: Boolean): Geometry {
        settle()
        val heading = visible(By.text(context.getString(R.string.home_recent))).visibleBounds
        return Geometry(
            Rect(visible(By.res("home-recent-panel")).visibleBounds),
            // Compose clips descendant accessibility bottoms during nested scrolling, without moving the heading.
            HeadingPosition(heading.left, heading.top, heading.right),
            if (withScan) Rect(visible(By.desc(context.getString(R.string.home_scan_to_pay))).visibleBounds) else null
        )
    }

    private fun scrollInsideHistory(count: Int, expected: Geometry, withScan: Boolean) {
        val list = visible(By.res("home-recent-list"))
        val before = visibleRecipients(list, count)
        assertTrue("History must expose visible fixture recipients before scrolling", before.isNotEmpty())
        val capturePrefix = "${if (withScan) "modern" else "classic"}-history-$count"
        screenshot("$capturePrefix-before-scroll")
        list.setGestureMargin((GESTURE_MARGIN_DP * context.resources.displayMetrics.density).toInt())
        // This boolean describes accessibility completion events, not whether visible records moved.
        list.scroll(Direction.DOWN, SCROLL_PORTION)
        settle()
        val after = visibleRecipients(visible(By.res("home-recent-list")), count)
        screenshot("$capturePrefix-after-scroll")
        if (after.none { it !in before }) dumpHierarchy("$capturePrefix-scroll-unchanged")
        assertTrue("Scrolling inside the box must reveal later records", after.any { it !in before })
        assertEquals("Scrolling history must not accidentally open a transaction", 0, transactionOpens.get())
        assertEquals("Only history contents should move", expected, geometry(withScan))
    }

    private fun visibleRecipients(list: UiObject2, count: Int): Set<String> =
        list.findObjects(recipientSelector(count))
            .filter { it.visibleBounds.height() > 0 }.map { it.text }.toSet()

    private fun recipientSelector(count: Int): BySelector =
        By.text(Pattern.compile(Pattern.quote("Fixture $count recipient") + ".*", Pattern.DOTALL))

    private fun assertListExtendsBehindScan() {
        val list = visible(By.res("home-recent-list")).visibleBounds
        val scan = visible(By.desc(context.getString(R.string.home_scan_to_pay))).visibleBounds
        assertTrue("The list must use the full card behind QR", list.bottom > scan.bottom)
        assertTrue(Rect.intersects(list, scan))
    }

    private fun assertLastRowCanClearScan(count: Int) {
        repeat(MAX_END_SWIPES) {
            val last = device.findObject(By.text(label(count, count - 1)))
            val scanTop = visible(By.desc(context.getString(R.string.home_scan_to_pay))).visibleBounds.top
            if (last != null && last.parent.visibleBounds.bottom <= scanTop) {
                screenshot("modern-last-row-clear")
                return
            }
            val bounds = visible(By.res("home-recent-list")).visibleBounds
            // Use the left side of the list so the floating QR never captures this drag.
            val inset = (GESTURE_MARGIN_DP * context.resources.displayMetrics.density).toInt()
            device.swipe(bounds.left + inset, bounds.bottom - inset,
                bounds.left + inset, bounds.top + inset, SWIPE_STEPS)
            settle()
        }
        assertTrue("The final payment must scroll fully clear of the floating QR", false)
    }

    private fun assertActionsReachable() {
        val priorScans = scans.get()
        val priorContacts = contacts.get()
        val priorHistory = historyOpens.get()
        visible(By.desc(context.getString(R.string.home_scan_to_pay))).click()
        visible(By.text(context.getString(R.string.home_view_all))).click()
        visible(By.desc(context.getString(R.string.home_scan))).click()
        visible(By.desc(context.getString(R.string.home_send))).click()
        settle()
        assertEquals(priorScans + 2, scans.get())
        assertEquals(priorContacts + 1, contacts.get())
        assertEquals(priorHistory + 1, historyOpens.get())
    }

    private fun revealWholeClassicCard() {
        repeat(MAX_REVEAL_SWIPES) {
            settle()
            val panel = visible(By.res("home-recent-panel")).visibleBounds
            if (panel.height() >= CLASSIC_HEIGHT_DP * context.resources.displayMetrics.density - 1) return
            // The outside gutter scrolls the page without touching the nested history list.
            val gutter = (GESTURE_MARGIN_DP * context.resources.displayMetrics.density).toInt()
            device.swipe(gutter, device.displayHeight * 3 / 4, gutter, device.displayHeight / 3, SWIPE_STEPS)
        }
        assertTrue("The complete Classic history box must be reachable", false)
    }

    private fun visible(selector: BySelector): UiObject2 {
        val control = device.wait(Until.findObject(selector), TIMEOUT_MS)
        if (control == null) {
            screenshot("missing-home-control")
            dumpHierarchy("missing-home-control")
        }
        requireNotNull(control) { "Missing home control: $selector" }
        assertTrue("Control needs visible bounds", control.visibleBounds.width() > 0 && control.visibleBounds.height() > 0)
        return control
    }

    private fun settle() {
        instrumentation.waitForIdleSync()
        device.waitForIdle()
        instrumentation.uiAutomation.clearCache()
    }

    private fun screenshot(name: String) {
        val directory = File(context.getExternalFilesDir(null), "refinement-home").apply { mkdirs() }
        assertTrue(device.takeScreenshot(File(directory, "$name.png")))
    }

    private fun dumpHierarchy(name: String) {
        val directory = File(context.getExternalFilesDir(null), "refinement-home").apply { mkdirs() }
        device.dumpWindowHierarchy(File(directory, "$name.xml"))
    }

    private fun label(count: Int, index: Int): String = "Fixture $count recipient ${index + 1}"

    companion object {
        private const val TIMEOUT_MS = 5000L
        private const val TEN_RECORDS = 10
        private const val THIRTY_RECORDS = 30
        private const val FIXTURE_TIMESTAMP = 1793701800000L
        private const val DAY_MS = 86400000L
        private const val GESTURE_MARGIN_DP = 8
        private const val SCROLL_PORTION = 0.75f
        private const val CLASSIC_HEIGHT_DP = 392
        private const val QR_BOTTOM_DP = 68
        private const val MAX_END_SWIPES = 12
        private const val MAX_REVEAL_SWIPES = 4
        private const val SWIPE_STEPS = 30
    }
}
