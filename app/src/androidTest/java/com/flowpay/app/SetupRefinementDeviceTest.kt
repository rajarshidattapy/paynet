// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app

import android.app.Activity
import android.app.Instrumentation
import android.animation.ValueAnimator
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.graphics.Rect
import android.os.Build
import android.view.WindowManager
import android.view.accessibility.AccessibilityNodeInfo
import androidx.activity.compose.setContent
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density
import androidx.lifecycle.Lifecycle
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleCallback
import androidx.test.runner.lifecycle.Stage
import androidx.test.uiautomator.By
import androidx.test.uiautomator.StaleObjectException
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.UiScrollable
import androidx.test.uiautomator.UiSelector
import androidx.test.uiautomator.Until
import com.flowpay.app.data.TestResults
import com.flowpay.app.data.TestResultsManager
import com.flowpay.app.helpers.SetupHelper
import com.flowpay.app.helpers.TestConfigurationHelper
import com.flowpay.app.helpers.OnboardingFlow
import com.flowpay.app.ui.activities.SettingsActivity
import com.flowpay.app.ui.home.HomeAppearance
import com.flowpay.app.ui.theme.BlueAccentTheme
import com.flowpay.app.ui.theme.FlowpayTheme
import com.flowpay.app.ui.theme.LocalFlowpayAccentTheme
import org.junit.After
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Focused UI checks for the refined onboarding. Run only against the isolated
 * debug application (-PisolatedDeviceTest); never against com.flowpay.app.
 * Call consent is accepted only to deny the fresh native permission prompt.
 * Blocking intent monitors prevent a dialing regression from opening Phone.
 * No system font/display settings are changed.
 */
@RunWith(AndroidJUnit4::class)
class SetupRefinementDeviceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext
    private val device = UiDevice.getInstance(instrumentation)
    private val preferences = context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE)
    private val resultsPreferences = context.getSharedPreferences("flowpay_test_results", Context.MODE_PRIVATE)
    private var savedPreferences: Map<String, *>? = null
    private var savedResults: Map<String, *>? = null
    private val scenarios = mutableListOf<ActivityScenario<out Activity>>()
    private var expectedBlockedCalls = 0
    private val callMonitors = mutableListOf<Instrumentation.ActivityMonitor>()
    private val externalViews = mutableListOf<Intent>()
    private val externalViewMonitor = object : Instrumentation.ActivityMonitor() {
        override fun onStartActivity(intent: Intent): Instrumentation.ActivityResult? {
            if (intent.action != Intent.ACTION_VIEW) return null
            synchronized(externalViews) { externalViews += Intent(intent) }
            return Instrumentation.ActivityResult(Activity.RESULT_CANCELED, null)
        }
    }
    private val createdActivities = mutableListOf<Activity>()
    private val lifecycleObserver = ActivityLifecycleCallback { activity, stage ->
        if (stage == Stage.CREATED && activity.packageName == context.packageName) {
            synchronized(createdActivities) { createdActivities += activity }
        }
    }

    @Before
    fun prepareIsolatedApp() {
        assumeTrue("Run with -PisolatedDeviceTest", context.packageName == "com.flowpay.app.setupcheck")
        assertEquals("Refusing to change production app state", "com.flowpay.app.setupcheck", context.packageName)
        savedPreferences = HashMap(preferences.all)
        savedResults = HashMap(resultsPreferences.all)
        preferences.edit().clear().commit()
        resultsPreferences.edit().clear().commit()
        instrumentation.addMonitor(externalViewMonitor)
        instrumentation.runOnMainSync {
            ActivityLifecycleMonitorRegistry.getInstance().addLifecycleCallback(lifecycleObserver)
        }
        for (action in listOf(Intent.ACTION_CALL, Intent.ACTION_DIAL,
            "android.intent.action.CALL_PRIVILEGED", "android.intent.action.CALL_EMERGENCY")) {
            val filter = IntentFilter(action).apply { addDataScheme("tel") }
            callMonitors += instrumentation.addMonitor(
                filter, Instrumentation.ActivityResult(Activity.RESULT_CANCELED, null), true
            )
        }
        device.wakeUp()
    }

    @After
    fun restoreIsolatedApp() {
        if (savedPreferences == null) return
        val callAttempts = callMonitors.sumOf { it.hits }
        try {
            instrumentation.runOnMainSync {
                ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED)
                    .toList().filter { it.packageName == context.packageName }.forEach { it.finish() }
            }
            scenarios.asReversed().forEach { it.close() }
            instrumentation.waitForIdleSync()
        } finally {
            instrumentation.runOnMainSync {
                ActivityLifecycleMonitorRegistry.getInstance().removeLifecycleCallback(lifecycleObserver)
            }
            callMonitors.forEach { instrumentation.removeMonitor(it) }
            instrumentation.removeMonitor(externalViewMonitor)
            savedPreferences?.let { restore(preferences, it) }
            savedResults?.let { restore(resultsPreferences, it) }
        }
        assertEquals("Only explicitly monitored setup handoffs are permitted", expectedBlockedCalls, callAttempts)
    }

    @Test
    fun scanSetupHandsOffOnceAcrossRecreation() {
        seedConfiguredBank()
        val scenario = launch(TestConfigurationActivity::class.java)
        instrumentation.uiAutomation.adoptShellPermissionIdentity(*PHONE_PERMISSIONS.toTypedArray())
        try {
            expectedBlockedCalls = 1
            repeat(2) {
                scenario.onActivity { configurationHelper(it).initiateCall(com.flowpay.app.managers.CallType.USSD) }
            }
            scenario.recreate()
            scenario.onActivity {
                val helper = configurationHelper(it)
                assertTrue(helper.getTestStates().ussdTesting)
                helper.initiateCall(com.flowpay.app.managers.CallType.USSD)
            }
            assertEquals(1, callMonitors.sumOf { it.hits })
        } finally {
            instrumentation.uiAutomation.dropShellPermissionIdentity()
        }
    }

    @Test
    fun nativePackageIncludesPaymentPermissionsWithoutSmsAccess() {
        @Suppress("DEPRECATION")
        val requested = context.packageManager.getPackageInfo(
            context.packageName, PackageManager.GET_PERMISSIONS
        ).requestedPermissions.orEmpty().toSet()
        val required = PHONE_PERMISSIONS + listOf(
            android.Manifest.permission.CAMERA,
            android.Manifest.permission.READ_CONTACTS,
            android.Manifest.permission.SYSTEM_ALERT_WINDOW
        )
        required.forEach { assertTrue("Missing native permission: $it", it in requested) }
        val messaging = listOf(
            android.Manifest.permission.READ_SMS,
            android.Manifest.permission.SEND_SMS,
            android.Manifest.permission.RECEIVE_SMS,
            android.Manifest.permission.RECEIVE_MMS,
            android.Manifest.permission.RECEIVE_WAP_PUSH
        )
        messaging.forEach { assertFalse("Unexpected messaging permission: $it", it in requested) }
    }

    @Test
    fun nativePhonePermissionIsRequestedBeforeDiallingAndCanBeDenied() {
        assertTrue("This check requires a fresh isolated permission state",
            PHONE_PERMISSIONS.all { context.checkSelfPermission(it) == android.content.pm.PackageManager.PERMISSION_DENIED })
        seedConfiguredBank()
        launch(TestConfigurationActivity::class.java)
        tag("config-ussd").click()
        tag("config-consent-start").click()
        val permissionPackage = java.util.regex.Pattern.compile("com\\.(google\\.)?android\\.permissioncontroller")
        val denySelector = By.res(java.util.regex.Pattern.compile(".*:id/permission_deny(_and_dont_ask_again)?_button"))
            .pkg(permissionPackage)
        val deny = device.wait(Until.findObject(denySelector), TIMEOUT)
        if (deny == null) {
            screenshot("native-phone-permission-missing")
            val directory = File(context.getExternalFilesDir(null), "setup-refinement").apply { mkdirs() }
            device.dumpWindowHierarchy(File(directory, "native-phone-permission-missing.xml"))
        }
        assertNotNull("Android must ask for phone permission before dialling", deny)
        val messageSelector = By.res(java.util.regex.Pattern.compile(".*:id/permission_message"))
            .pkg(permissionPackage)
        val appLabel = context.applicationInfo.loadLabel(context.packageManager)
        assertEquals("Allow $appLabel to make and manage phone calls?", device.findObject(messageSelector)?.text)
        screenshot("native-phone-permission")
        deny!!.click()
        assertTrue("Native permission prompt did not dismiss", device.wait(Until.gone(denySelector), TIMEOUT))
        assertEquals("Permission denial must not place a call", 0, callMonitors.sumOf { it.hits })
        assertTrue(PHONE_PERMISSIONS.all {
            context.checkSelfPermission(it) == android.content.pm.PackageManager.PERMISSION_DENIED
        })
        assertNull(TestResultsManager(context).getTestResults())
        assertFalse(preferences.getBoolean("test_configuration_completed", false))
        assertRemains(TestConfigurationActivity::class.java)
        assertEquals("Permission denial must not advance onboarding", 0, createdCount(MainActivity::class.java))
    }

    @Test
    fun incompleteSetupAndReadingDisclaimerNeverAdvance() {
        launch(SetupActivity::class.java)
        assertRemovedControlsAbsent()
        assertRemains(SetupActivity::class.java)
        select("setup-bank", "State Bank of India")
        assertRemains(SetupActivity::class.java)
        select("setup-primary-sim", "Airtel")
        assertChecked("setup-disclaimer", false)

        text(context.getString(R.string.setup_refined_read_disclaimer)).click()
        assertTrue(device.wait(Until.hasObject(By.text(context.getString(R.string.setup_refined_hide_disclaimer))), TIMEOUT))
        assertChecked("setup-disclaimer", false)
        assertRemains(SetupActivity::class.java)
        text(context.getString(R.string.setup_refined_hide_disclaimer)).click()
        assertRemains(SetupActivity::class.java)
        assertFalse(preferences.getBoolean("setup_completed", false))
        assertEquals(0, createdCount(TestConfigurationActivity::class.java))
    }

    @Test
    fun explicitConsentCompletesValidSetupAndAdvancesExactlyOnce() {
        launch(SetupActivity::class.java)
        select("setup-bank", "State Bank of India")
        select("setup-primary-sim", "Airtel")
        assertRemains(SetupActivity::class.java)
        tag("setup-disclaimer").click()
        awaitActivity(TestConfigurationActivity::class.java)
        assertRemains(TestConfigurationActivity::class.java)
        assertEquals("Setup must open configuration only once", 1, createdCount(TestConfigurationActivity::class.java))
        assertEquals("sbi", preferences.getString("selected_bank", null))
        assertEquals("airtel", preferences.getString("selected_primary_sim", null))
        assertTrue(preferences.getBoolean("disclaimer_accepted", false))
        assertTrue(preferences.getBoolean("setup_completed", false))
        assertFalse(preferences.getBoolean("test_configuration_completed", false))
        assertEquals(0, createdCount(MainActivity::class.java))
    }

    @Test
    fun withdrawingConsentDuringTheCompletionPauseCancelsNavigationAcrossRecreation() {
        assumeTrue("Reduced motion intentionally skips the completion pause", ValueAnimator.areAnimatorsEnabled())
        val scenario = launch(SetupActivity::class.java)
        select("setup-bank", "State Bank of India")
        select("setup-primary-sim", "Airtel")
        tag("setup-disclaimer")

        // Use native accessibility actions without UiAutomator's idle wait:
        // both changes must happen inside the brief, user-visible settle window.
        val checkbox = requireNotNull(accessibilityNode("setup-disclaimer"))
        assertTrue(checkbox.performAction(AccessibilityNodeInfo.ACTION_CLICK))
        val acceptedBy = android.os.SystemClock.elapsedRealtime() + 250L
        var accepted: AccessibilityNodeInfo? = null
        while (accepted == null && android.os.SystemClock.elapsedRealtime() < acceptedBy) {
            accepted = accessibilityNode("setup-disclaimer")?.takeIf { it.isChecked }
            if (accepted == null) android.os.SystemClock.sleep(10)
        }
        assertNotNull("The first action must explicitly accept before it is withdrawn", accepted)
        assertTrue(accepted!!.performAction(AccessibilityNodeInfo.ACTION_CLICK))
        assertChecked("setup-disclaimer", false)
        assertRemains(SetupActivity::class.java)
        assertEquals(0, createdCount(TestConfigurationActivity::class.java))
        scenario.recreate()
        assertChecked("setup-disclaimer", false)
        assertRemains(SetupActivity::class.java)
        assertFalse(preferences.getBoolean("setup_completed", false))

        tag("setup-disclaimer").click()
        awaitActivity(TestConfigurationActivity::class.java)
        assertRemains(TestConfigurationActivity::class.java)
        assertEquals("A fresh acceptance must advance only once", 1, createdCount(TestConfigurationActivity::class.java))
    }

    @Test
    fun legacyTwoSimPreferencesNeverAddHiddenSetupRequirements() {
        preferences.edit().putBoolean("is_dual_sim_enabled", true)
            .putString("selected_secondary_sim", "").commit()
        val scenario = launch(SetupActivity::class.java)
        select("setup-bank", "State Bank of India")
        select("setup-primary-sim", "Airtel")
        assertFalse(device.hasObject(By.res("setup-dual-sim")))
        assertFalse(device.hasObject(By.res("setup-secondary-sim")))
        assertChecked("setup-disclaimer", false)
        scenario.recreate()
        assertField("setup-bank", "State Bank of India")
        assertField("setup-primary-sim", "Airtel")
        assertFalse(device.hasObject(By.text("Use two SIMs")))
        assertFalse(device.hasObject(By.res("setup-secondary-sim")))
        assertChecked("setup-disclaimer", false)
        tag("setup-disclaimer").click()
        awaitActivity(TestConfigurationActivity::class.java)
        assertRemains(TestConfigurationActivity::class.java)
        assertEquals(1, createdCount(TestConfigurationActivity::class.java))
        assertEquals("airtel", preferences.getString("selected_primary_sim", null))
        assertEquals("", preferences.getString("selected_secondary_sim", null))
        assertTrue(preferences.getBoolean("is_dual_sim_enabled", false))
    }

    @Test
    fun uncheckedConfigurationStaysOnScreenAcrossRecreation() {
        seedConfiguredBank()
        val scenario = launch(TestConfigurationActivity::class.java)
        assertRemovedControlsAbsent()
        assertRemains(TestConfigurationActivity::class.java)
        assertFalse(hasCompletedIndicator("config-ussd"))
        assertFalse(hasCompletedIndicator("config-upi123"))
        scenario.recreate()
        assertRemains(TestConfigurationActivity::class.java)
        assertNull(TestResultsManager(context).getTestResults())
        assertFalse(preferences.getBoolean("test_configuration_completed", false))
        assertEquals(0, createdCount(MainActivity::class.java))
        assertEquals("Recreation should create only one replacement", 2, createdCount(TestConfigurationActivity::class.java))
    }

    @Test
    fun eitherPartialResultRequiresTheOtherConfirmationBeforeAdvancing() {
        for ((ussd, upi123) in listOf(true to false, false to true)) {
            seedConfiguredBank()
            TestResultsManager(context).saveTestResults(TestResults(ussdEnabled = ussd, upi123Enabled = upi123))
            val previousHomes = createdCount(MainActivity::class.java)
            val scenario = launch(TestConfigurationActivity::class.java)
            assertRemains(TestConfigurationActivity::class.java)
            assertEquals("USSD completion must survive reopening", ussd, hasCompletedIndicator("config-ussd"))
            assertEquals("UPI 123 completion must survive reopening", upi123, hasCompletedIndicator("config-upi123"))
            assertEquals(previousHomes, createdCount(MainActivity::class.java))
            scenario.recreate()
            assertRemains(TestConfigurationActivity::class.java)
            assertFalse(preferences.getBoolean("test_configuration_completed", false))

            // Simulate the user's post-call confirmation, without starting a call.
            scenario.onActivity { activity ->
                val helper = configurationHelper(activity)
                if (!ussd) helper.handleUssdConfigurationConfirmation(true)
                else helper.handleUpi123ConfigurationConfirmation(true)
            }
            awaitActivity(MainActivity::class.java)
            assertRemains(MainActivity::class.java)
            assertEquals("The final confirmation must open home once", previousHomes + 1, createdCount(MainActivity::class.java))
            assertResults(ussd = true, upi123 = true)
            assertTrue(preferences.getBoolean("test_configuration_completed", false))
            closeResumedActivity()
            scenario.close()
        }
    }

    @Test
    fun alreadyReadyConfigurationAdvancesOnceAndHomeRecreationDoesNotLoop() {
        seedConfiguredBank()
        TestResultsManager(context).saveTestResults(TestResults(ussdEnabled = true, upi123Enabled = true))
        // This Activity may finish before ActivityScenario can run onActivity.
        launch(TestConfigurationActivity::class.java, mayAdvanceImmediately = true)
        awaitActivity(MainActivity::class.java)
        assertRemains(MainActivity::class.java)
        assertEquals(1, createdCount(MainActivity::class.java))
        assertEquals(1, createdCount(TestConfigurationActivity::class.java))
        instrumentation.runOnMainSync {
            resumedActivities().single { it is MainActivity }.recreate()
        }
        val recreatedBy = android.os.SystemClock.elapsedRealtime() + TIMEOUT
        while (createdCount(MainActivity::class.java) < 2 && android.os.SystemClock.elapsedRealtime() < recreatedBy) {
            android.os.SystemClock.sleep(50)
        }
        awaitActivity(MainActivity::class.java)
        assertRemains(MainActivity::class.java)
        assertEquals("Home recreation must not trigger more onboarding launches", 1, createdCount(TestConfigurationActivity::class.java))
        assertEquals("Home should have exactly one replacement", 2, createdCount(MainActivity::class.java))
        assertResults(ussd = true, upi123 = true)
    }

    @Test
    fun jioRequiresUpiConfirmationAndNeverSavesUnavailableUssdAsComplete() {
        seedConfiguredBank()
        preferences.edit().putString("selected_primary_sim", "jio").commit()
        val scenario = launch(TestConfigurationActivity::class.java)
        assertRemains(TestConfigurationActivity::class.java)
        assertEnabled("config-ussd", false, "An unavailable USSD method must not offer a call")
        assertTrue(device.hasObject(By.text("Unavailable on Jio")))
        assertFalse(hasCompletedIndicator("config-ussd"))
        assertEnabled("config-upi123", true)
        assertEquals(0, createdCount(MainActivity::class.java))
        scenario.onActivity { configurationHelper(it).handleUpi123ConfigurationConfirmation(true) }
        awaitActivity(MainActivity::class.java)
        assertRemains(MainActivity::class.java)
        assertEquals(1, createdCount(MainActivity::class.java))
        assertResults(ussd = false, upi123 = true)
    }

    @Test
    fun explicitUssdWaiverStillRequiresUpiConfirmation() {
        seedConfiguredBank()
        preferences.edit().putBoolean("user_reported_ussd_not_working", true).commit()
        val scenario = launch(TestConfigurationActivity::class.java)
        assertRemains(TestConfigurationActivity::class.java)
        assertFalse(hasCompletedIndicator("config-ussd"))
        assertEquals(0, createdCount(MainActivity::class.java))
        scenario.onActivity { configurationHelper(it).handleUpi123ConfigurationConfirmation(true) }
        awaitActivity(MainActivity::class.java)
        assertRemains(MainActivity::class.java)
        assertEquals(1, createdCount(MainActivity::class.java))
        assertResults(ussd = false, upi123 = true)
    }

    @Test
    fun pendingCallConsentBlocksNavigationUntilDismissed() {
        seedConfiguredBank()
        TestResultsManager(context).saveTestResults(TestResults(ussdEnabled = true, upi123Enabled = false))
        val scenario = launch(TestConfigurationActivity::class.java)
        tag("config-upi123").click()
        tag("config-consent-cancel")
        scenario.onActivity { configurationHelper(it).handleUpi123ConfigurationConfirmation(true) }
        assertRemains(TestConfigurationActivity::class.java)
        assertEquals("A pending dialog must keep its screen alive", 0, createdCount(MainActivity::class.java))
        tag("config-consent-cancel").click()
        awaitActivity(MainActivity::class.java)
        assertRemains(MainActivity::class.java)
        assertEquals(1, createdCount(MainActivity::class.java))
        assertResults(ussd = true, upi123 = true)
    }

    @Test
    fun cancellingEitherCallConsentLeavesConfigurationUntouched() {
        seedConfiguredBank()
        launch(TestConfigurationActivity::class.java)
        val permissionsBefore = PHONE_PERMISSIONS.map { context.checkSelfPermission(it) }
        for (method in listOf("config-ussd", "config-upi123")) {
            tag(method).click()
            val cancel = tag("config-consent-cancel")
            val title = if (method == "config-ussd") R.string.onboarding_scan_call_title else R.string.onboarding_contact_call_title
            val message = if (method == "config-ussd") R.string.onboarding_scan_call_message else R.string.onboarding_contact_call_message
            assertTrue(device.hasObject(By.text(context.getString(title))))
            assertTrue(device.hasObject(By.text(context.getString(message))))
            assertTrue(device.hasObject(By.text(context.getString(R.string.onboarding_call_pin_note))))
            assertFalse("The setup modal must not restore the removed charges copy", device.hasObject(By.textContains("charge")))
            screenshot("$method-consent")
            assertEquals(0, callMonitors.sumOf { it.hits })
            cancel.click()
            assertTrue(device.wait(Until.gone(By.res("config-consent-cancel")), TIMEOUT))
            assertRemains(TestConfigurationActivity::class.java)
            assertEnabled(method, true)
            assertNull(TestResultsManager(context).getTestResults())
            assertEquals(0, createdCount(MainActivity::class.java))
        }
        assertEquals(permissionsBefore, PHONE_PERMISSIONS.map { context.checkSelfPermission(it) })
        assertFalse(preferences.getBoolean("test_configuration_completed", false))
    }

    @Test
    fun paymentBackOpensEditableReviewWithoutBouncingAndSavesAChangedBank() {
        seedConfiguredBank()
        TestResultsManager(context).saveTestResults(TestResults(ussdEnabled = true, upi123Enabled = false))
        launch(TestConfigurationActivity::class.java)
        assertTouchTarget("config-back")
        tag("config-back").click()
        awaitActivity(SetupActivity::class.java)
        assertRemains(SetupActivity::class.java)
        assertField("setup-bank", "State Bank of India")
        assertField("setup-primary-sim", "Airtel")
        assertChecked("setup-disclaimer", true)
        assertEquals("Review must not immediately reopen payment setup", 1, createdCount(TestConfigurationActivity::class.java))

        text(context.getString(R.string.setup_refined_read_disclaimer)).click()
        assertRemains(SetupActivity::class.java)
        text(context.getString(R.string.setup_refined_hide_disclaimer)).click()
        tag("setup-bank").click()
        device.pressBack()
        assertRemains(SetupActivity::class.java)
        recreateResumed(SetupActivity::class.java)
        assertRemains(SetupActivity::class.java)
        assertField("setup-bank", "State Bank of India")
        assertChecked("setup-disclaimer", true)

        select("setup-bank", "HDFC Bank", advances = true)
        awaitActivity(TestConfigurationActivity::class.java)
        assertRemains(TestConfigurationActivity::class.java)
        assertEquals("hdfc", preferences.getString("selected_bank", null))
        assertEquals("airtel", preferences.getString("selected_primary_sim", null))
        assertEquals(2, createdCount(TestConfigurationActivity::class.java))
        assertNull("A changed bank must discard stale readiness", TestResultsManager(context).getTestResults())
        assertFalse(preferences.getBoolean("test_configuration_completed", false))
        assertEquals(0, createdCount(MainActivity::class.java))

        device.pressBack()
        awaitActivity(SetupActivity::class.java)
        assertRemains(SetupActivity::class.java)
        assertField("setup-bank", "HDFC Bank")
        assertEquals("System Back must use the same non-bouncing review path", 2,
            createdCount(TestConfigurationActivity::class.java))
    }

    @Test
    fun completedPaymentsRequireAppearanceChoiceThenWelcomeAndHomeExactlyOnce() {
        for (classic in listOf(false, true)) {
            seedConfiguredBank(appearanceComplete = false)
            TestResultsManager(context).saveTestResults(TestResults(ussdEnabled = true, upi123Enabled = true))
            val appearance = HomeAppearance(classic = !classic, monochrome = classic)
            appearance.save(context)
            val homesBefore = createdCount(MainActivity::class.java)
            val chooserBefore = createdCount(AppearanceSetupActivity::class.java)
            val configuration = launch(TestConfigurationActivity::class.java, mayAdvanceImmediately = true)
            awaitActivity(AppearanceSetupActivity::class.java)
            assertRemains(AppearanceSetupActivity::class.java)
            assertEquals(homesBefore, createdCount(MainActivity::class.java))
            assertTouchTarget("appearance-modern")
            assertTouchTarget("appearance-classic")
            screenshot(if (classic) "appearance-choose-classic" else "appearance-choose-modern")

            tag(if (classic) "appearance-classic" else "appearance-modern").click()
            // Do not wait for accessibility idle across this deliberately brief
            // animation. Reduced-motion devices are checked through persistence
            // and navigation instead of requiring a transient animation frame.
            if (ValueAnimator.areAnimatorsEnabled()) {
                val welcome = device.wait(Until.findObject(By.res("welcome-content")), TIMEOUT)
                assertNotNull("The chosen layout must introduce the welcome screen", welcome)
                // Capture the greeting after its entrance, rather than the transparent first frame.
                android.os.SystemClock.sleep(800L)
                val title = device.findObject(By.res("welcome-title"))
                assertNotNull("The greeting must be visible during its hold", title)
                assertEquals("Hello, offline\npayments.", title!!.text)
                assertFalse(device.hasObject(By.res("welcome-subtitle")))
                screenshotNow(if (classic) "welcome-classic" else "welcome-modern")
            }
            awaitActivity(MainActivity::class.java)
            assertRemains(MainActivity::class.java)
            assertEquals(homesBefore + 1, createdCount(MainActivity::class.java))
            assertEquals(chooserBefore + 1, createdCount(AppearanceSetupActivity::class.java))
            assertEquals(HomeAppearance(classic = classic, monochrome = !classic), HomeAppearance.read(context))
            assertTrue(preferences.getBoolean(OnboardingFlow.APPEARANCE_COMPLETED, false))
            assertTrue(preferences.getBoolean(OnboardingFlow.WELCOME_COMPLETED, false))
            assertResults(ussd = true, upi123 = true)
            screenshot(if (classic) "home-classic-og-blue" else "home-modern-monochrome")
            closeResumedActivity()
            configuration.close()
        }
    }

    @Test
    fun welcomePausesInBackgroundAndBackReturnsToChoiceThenSetupReview() {
        seedConfiguredBank(appearanceComplete = false)
        preferences.edit().putBoolean("test_configuration_completed", true).commit()
        TestResultsManager(context).saveTestResults(TestResults(ussdEnabled = true, upi123Enabled = true))
        val scenario = launch(AppearanceSetupActivity::class.java)
        tag("appearance-classic").click()
        scenario.moveToState(Lifecycle.State.CREATED)
        // Longer than either welcome duration: backgrounding must suspend the
        // completion action rather than mark onboarding complete offscreen.
        val pauseUntil = android.os.SystemClock.elapsedRealtime() + 3000L
        while (android.os.SystemClock.elapsedRealtime() < pauseUntil) {
            assertEquals(0, createdCount(MainActivity::class.java))
            assertFalse(preferences.getBoolean(OnboardingFlow.WELCOME_COMPLETED, false))
            android.os.SystemClock.sleep(50)
        }
        scenario.recreate()
        assertEquals(0, createdCount(MainActivity::class.java))
        scenario.moveToState(Lifecycle.State.RESUMED)
        scenario.onActivity { it.onBackPressedDispatcher.onBackPressed() }
        assertRemains(AppearanceSetupActivity::class.java)
        tag("appearance-modern")
        tag("appearance-classic")
        assertFalse(preferences.getBoolean(OnboardingFlow.APPEARANCE_COMPLETED, true))
        assertFalse(preferences.getBoolean(OnboardingFlow.WELCOME_COMPLETED, true))
        assertTrue("Reviewing the choice must retain its saved layout", HomeAppearance.read(context).classic)
        scenario.onActivity { it.onBackPressedDispatcher.onBackPressed() }
        awaitActivity(SetupActivity::class.java)
        assertRemains(SetupActivity::class.java)
        assertField("setup-bank", "State Bank of India")
        assertChecked("setup-disclaimer", true)
        assertEquals(0, createdCount(TestConfigurationActivity::class.java))
        assertEquals(0, createdCount(MainActivity::class.java))
    }

    @Test
    fun settingsThemeAndLayoutPersistWithoutChangingPaymentSetup() {
        seedConfiguredBank()
        HomeAppearance().save(context)
        preferences.edit().putBoolean("test_configuration_completed", true).commit()
        TestResultsManager(context).saveTestResults(TestResults(ussdEnabled = true, upi123Enabled = true))
        val scenario = launch(SettingsActivity::class.java)
        tag("settings-icon")
        assertFalse("Settings should use its cog instead of a repeated heading", device.hasObject(By.text("Settings")))
        assertTouchTarget("settings-color-theme")
        tag("settings-color-theme").click()
        assertTrue(device.wait(Until.hasObject(By.text("OG Blue")), TIMEOUT))
        assertFalse("Theme switches directly without a picker", device.hasObject(By.res("settings-color-dialog")))
        assertFalse(HomeAppearance.read(context).monochrome)
        assertFalse(HomeAppearance.read(context).classic)
        assertTouchTarget("settings-home-design")
        tag("settings-home-design").click()
        assertTrue(device.wait(Until.hasObject(By.text("Classic")), TIMEOUT))
        assertFalse("Design switches directly without a picker", device.hasObject(By.res("settings-design-dialog")))
        scenario.recreate()
        assertRemains(SettingsActivity::class.java)
        assertTrue(HomeAppearance.read(context).classic)
        assertFalse("Changing design preserves the selected color", HomeAppearance.read(context).monochrome)
        assertEquals("sbi", preferences.getString("selected_bank", null))
        assertTrue(preferences.getBoolean("test_configuration_completed", false))
        assertResults(ussd = true, upi123 = true)
        screenshot("settings-direct-blue-classic")

        tag("settings-home-design").click()
        assertTrue(device.wait(Until.hasObject(By.text("Modern")), TIMEOUT))
        assertFalse(HomeAppearance.read(context).classic)
        assertFalse("Changing back still preserves blue", HomeAppearance.read(context).monochrome)
        tag("settings-color-theme").click()
        assertTrue(device.wait(Until.hasObject(By.text("Black & White")), TIMEOUT))
        scenario.recreate()
        assertFalse(HomeAppearance.read(context).classic)
        assertTrue(HomeAppearance.read(context).monochrome)
        assertEquals("sbi", preferences.getString("selected_bank", null))
        assertResults(ussd = true, upi123 = true)
        screenshot("settings-direct-monochrome-modern")
    }

    @Test
    fun settingsOfficialSheetUsesProjectLinkAndCancellingResetPreservesData() {
        seedConfiguredBank()
        val savedSetup = preferences.all.toMap()
        val savedResults = resultsPreferences.all.toMap()
        launch(SettingsActivity::class.java)
        tag("settings-version").click()
        tag("settings-version-dialog")
        val officialMessage = "This is the official APK distributed by Flowpay. It does not include SMS parsing. " +
            "For the SMS parsing version, visit our GitHub project."
        assertTrue("The official build must clearly explain its SMS scope", device.hasObject(By.text(officialMessage)))
        assertFalse(device.hasObject(By.text("Our roots")))
        screenshot("settings-official-build")
        tag("settings-github").click()
        assertExternalView("https://github.com/Flowpayup/Payments-Without-Internet", expectedCount = 1)
        assertRemains(SettingsActivity::class.java)
        device.pressBack()
        assertTrue(device.wait(Until.gone(By.res("settings-version-dialog")), TIMEOUT))
        assertFalse(device.hasObject(By.res("settings-our-roots")))

        val reset = tag("settings-clear-app-data")
        assertFalse("Settings must omit the Android OS version row", device.hasObject(By.text("Android")))
        screenshot("settings-about")
        reset.click()
        tag("settings-clear-dialog")
        assertTouchTarget("settings-confirm-clear")
        screenshot("settings-reset-confirmation")
        device.pressBack()
        assertTrue(device.wait(Until.gone(By.res("settings-clear-dialog")), TIMEOUT))
        assertRemains(SettingsActivity::class.java)
        assertEquals("Cancelling reset must preserve setup and appearance", savedSetup, preferences.all)
        assertEquals("Cancelling reset must preserve payment readiness", savedResults, resultsPreferences.all)
    }

    @Test
    fun bothThemesAndLargeTextKeepOnboardingHeadingsAlignedAndControlsReachable() {
        for (monochrome in listOf(true, false)) {
            val theme = if (monochrome) "home-monochrome" else "home-blue"
            HomeAppearance(monochrome = monochrome).save(context)
            val setup = launch(SetupActivity::class.java)
            scrollToTop()
            val setupHeader = headerBounds("setup")
            assertRemovedControlsAbsent()
            screenshot("setup-$theme")
            assertSetupFieldsReachable()
            assertEquals(monochrome, HomeAppearance.read(context).monochrome)
            setup.close()

            seedConfiguredBank()
            val configuration = launch(TestConfigurationActivity::class.java)
            scrollToTop()
            assertConfigurationHeader()
            assertHeadersAligned(setupHeader, headerBounds("config"))
            assertRemovedControlsAbsent()
            screenshot("configuration-$theme")
            assertConfigurationMethodsReachable()
            assertEquals(monochrome, HomeAppearance.read(context).monochrome)
            configuration.close()
            clearSetupSelections()
        }

        val setup = launch(SetupActivity::class.java)
        setup.onActivity { activity ->
            val density = activity.resources.displayMetrics.density
            val helper = SetupActivity::class.java.getDeclaredField("setupHelper")
                .apply { isAccessible = true }.get(activity) as SetupHelper
            activity.setContent {
                CompositionLocalProvider(
                    LocalDensity provides Density(density, 1.5f),
                    LocalFlowpayAccentTheme provides BlueAccentTheme
                ) { FlowpayTheme { SetupScreen(helper) } }
            }
        }
        scrollToTop()
        screenshot("setup-large-text")
        assertSetupFieldsReachable()
        screenshot("setup-large-text-controls")
        assertRemovedControlsAbsent()
        setup.close()

        seedConfiguredBank()
        val configuration = launch(TestConfigurationActivity::class.java)
        configuration.onActivity { activity ->
            val density = activity.resources.displayMetrics.density
            val helper = configurationHelper(activity)
            activity.setContent {
                CompositionLocalProvider(
                    LocalDensity provides Density(density, 1.5f),
                    LocalFlowpayAccentTheme provides BlueAccentTheme
                ) { FlowpayTheme { TestConfigurationScreen(helper) } }
            }
        }
        scrollToTop()
        assertConfigurationHeader()
        screenshot("configuration-large-text")
        assertConfigurationMethodsReachable()
        screenshot("configuration-large-text-controls")
        assertRemovedControlsAbsent()
        configuration.close()
    }

    private fun assertConfigurationHeader() {
        assertTrue("Configuration must explain its purpose", device.hasObject(By.text("Set up payments")))
        for (oldCopy in listOf("Test setup", "Test Configuration", "Step 2 of 2", "Configure Payment Methods")) {
            assertFalse("Obsolete configuration copy: $oldCopy", device.hasObject(By.text(oldCopy)))
        }
    }

    private fun assertRemovedControlsAbsent() {
        refreshUi()
        for (name in listOf("setup-continue", "config-continue", "config-skip")) {
            assertFalse("Onboarding must not require the removed $name action", device.hasObject(By.res(name)))
        }
    }

    private fun headerBounds(screen: String): Pair<Rect, Rect> {
        val icon = Rect(tag("$screen-icon").visibleBounds)
        val title = Rect(tag("$screen-title").visibleBounds)
        val viewport = tag("$screen-content").visibleBounds
        assertTrue("The $screen glyph must stay in its safe viewport", viewport.contains(icon))
        assertTrue("The $screen title must stay in its safe viewport", viewport.contains(title))
        return icon to title
    }

    private fun assertHeadersAligned(setup: Pair<Rect, Rect>, configuration: Pair<Rect, Rect>) {
        val tolerance = 4 * context.resources.displayMetrics.density
        for ((name, positions) in listOf("glyph" to (setup.first to configuration.first),
            "title" to (setup.second to configuration.second))) {
            assertTrue("The $name must not jump vertically between onboarding screens",
                kotlin.math.abs(positions.first.top - positions.second.top) <= tolerance)
            assertTrue("The $name must retain its horizontal alignment",
                kotlin.math.abs(positions.first.centerX() - positions.second.centerX()) <= tolerance)
        }
    }

    private fun assertSetupFieldsReachable() {
        for (name in listOf("setup-bank", "setup-primary-sim", "setup-disclaimer")) {
            assertTouchTarget(name)
            assertTrue("$name must remain actionable", tag(name).isClickable)
        }
        assertFalse("The removed two-SIM control must not return", device.hasObject(By.res("setup-dual-sim")))
        assertFalse(device.hasObject(By.res("setup-secondary-sim")))
        assertRemains(SetupActivity::class.java)
    }

    private fun assertConfigurationMethodsReachable() {
        assertTouchTarget("config-back")
        for (name in listOf("config-ussd", "config-upi123")) {
            assertTouchTarget(name)
            val control = tag(name)
            assertTrue("Available methods must remain actionable", control.isEnabled && control.isClickable)
            val bounds = Rect(control.visibleBounds)
            val viewport = tag("config-content").visibleBounds
            assertTrue("The method must be fully reachable inside its viewport", viewport.contains(bounds))
        }
        assertRemains(TestConfigurationActivity::class.java)
    }

    private fun configurationHelper(activity: TestConfigurationActivity): TestConfigurationHelper =
        TestConfigurationActivity::class.java.getDeclaredField("testHelper")
            .apply { isAccessible = true }.get(activity) as TestConfigurationHelper

    private fun clearSetupSelections() {
        preferences.edit().remove("selected_bank").remove("selected_primary_sim")
            .remove("selected_secondary_sim").remove("is_dual_sim_enabled")
            .remove("setup_completed").remove("disclaimer_accepted").commit()
    }

    private fun assertResults(ussd: Boolean, upi123: Boolean) {
        val saved = TestResultsManager(context).getTestResults()
        assertNotNull(saved)
        assertEquals(ussd, saved!!.ussdEnabled)
        assertEquals(upi123, saved.upi123Enabled)
    }

    private fun <T : Activity> launch(type: Class<T>, mayAdvanceImmediately: Boolean = false): ActivityScenario<T> {
        val scenario = ActivityScenario.launch(type)
        scenarios += scenario
        if (!mayAdvanceImmediately) {
            scenario.onActivity { it.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
        }
        refreshUi()
        return scenario
    }

    private fun seedConfiguredBank(appearanceComplete: Boolean = true) {
        preferences.edit().putString("selected_bank", "sbi")
            .putString("selected_primary_sim", "airtel")
            .putBoolean("is_dual_sim_enabled", false).putString("selected_secondary_sim", "")
            .putBoolean("setup_completed", true).putBoolean("disclaimer_accepted", true)
            .putBoolean("test_configuration_completed", false)
            .putBoolean("appearance_setup_completed", appearanceComplete)
            .putBoolean("welcome_completed", appearanceComplete)
            .putBoolean("user_reported_ussd_not_working", false).commit()
    }

    private fun tag(name: String): UiObject2 {
        refreshUi()
        val selector = By.res(name)
        val current = device.findObject(selector)
        if (current == null || current.visibleBounds.height() < 32 * context.resources.displayMetrics.density) {
            scrollIntoViewIfAvailable(UiSelector().resourceId(name))
        }
        if (!device.hasObject(selector)) {
            // Some Compose versions omit an offscreen disabled action from
            // scrollIntoView's search. Exercise the same swipe a user makes.
            scrollToTop()
            for (attempt in 0 until 6) {
                refreshUi()
                if (device.hasObject(selector)) break
                device.swipe(device.displayWidth / 2, device.displayHeight * 3 / 4,
                    device.displayWidth / 2, device.displayHeight / 3, 20)
                refreshUi()
            }
        }
        refreshUi()
        val found = device.wait(Until.findObject(selector), TIMEOUT)
        if (found == null) {
            val directory = File(context.getExternalFilesDir(null), "setup-refinement").apply { mkdirs() }
            device.takeScreenshot(File(directory, "missing-$name.png"))
            device.dumpWindowHierarchy(File(directory, "missing-$name.xml"))
        }
        return requireNotNull(found) { "Missing control: $name" }
    }

    private fun text(value: String): UiObject2 {
        refreshUi()
        if (!device.hasObject(By.text(value))) {
            scrollIntoViewIfAvailable(UiSelector().text(value))
        }
        return requireNotNull(device.wait(Until.findObject(By.text(value)), TIMEOUT)) { "Missing text: $value" }
    }

    private fun select(field: String, label: String, advances: Boolean = false) {
        tag(field).click()
        val deadline = android.os.SystemClock.elapsedRealtime() + TIMEOUT
        var option: UiObject2? = null
        while (option == null && android.os.SystemClock.elapsedRealtime() < deadline) {
            try {
                refreshUi()
                // A selected SIM elsewhere on the form can have this same text.
                // Menu items have a clickable ancestor outside all setup fields.
                option = device.findObjects(By.text(label))
                    .mapNotNull(::popupItemAncestor)
                    .distinctBy { it.visibleBounds }
                    .singleOrNull()
            } catch (_: StaleObjectException) {
                // Compose may replace the accessibility nodes while opening the popup.
            }
            if (option == null) android.os.SystemClock.sleep(50)
        }
        requireNotNull(option) { "Missing unambiguous popup option: $label" }.click()
        refreshUi()
        if (!advances) assertField(field, label)
    }

    private fun popupItemAncestor(candidate: UiObject2): UiObject2? {
        var node: UiObject2? = candidate
        var clickable: UiObject2? = null
        while (node != null) {
            val resource = node.resourceName
            if (SETUP_FIELDS.any { tag -> resource == tag || resource?.endsWith("/$tag") == true }) {
                return null
            }
            if (clickable == null && node.isClickable) clickable = node
            node = node.parent
        }
        return clickable
    }

    private fun assertField(field: String, expected: String) {
        tag(field)
        val deadline = android.os.SystemClock.elapsedRealtime() + TIMEOUT
        var matched = false
        while (!matched && android.os.SystemClock.elapsedRealtime() < deadline) {
            try {
                refreshUi()
                val control = device.findObject(By.res(field))
                matched = control != null && (control.text == expected || control.hasObject(By.text(expected)))
            } catch (_: StaleObjectException) {
                // Wait for the selected value to settle after popup dismissal/recreation.
            }
            if (!matched) android.os.SystemClock.sleep(50)
        }
        assertTrue("$field did not retain $expected", matched)
    }

    private fun assertChecked(name: String, expected: Boolean) {
        assertControlState(name, "$name checked state must be $expected") { it.isChecked == expected }
    }

    private fun assertEnabled(name: String, expected: Boolean, message: String = "$name enabled state must be $expected") {
        assertControlState(name, message) { it.isEnabled == expected }
    }

    private fun assertControlState(name: String, message: String, matches: (UiObject2) -> Boolean) {
        tag(name)
        val deadline = android.os.SystemClock.elapsedRealtime() + TIMEOUT
        var matched = false
        while (!matched && android.os.SystemClock.elapsedRealtime() < deadline) {
            try {
                refreshUi()
                matched = device.findObject(By.res(name))?.let(matches) == true
            } catch (_: StaleObjectException) {
                // Reacquire the node after Compose updates the selected/disabled state.
            }
            if (!matched) android.os.SystemClock.sleep(50)
        }
        assertTrue(message, matched)
    }

    private fun hasCompletedIndicator(name: String): Boolean {
        val control = tag(name)
        return control.contentDescription.orEmpty().contains("Completed") || control.hasObject(By.desc("Completed"))
    }

    private fun assertTouchTarget(name: String) {
        val control = tag(name)
        val minimum = 43 * context.resources.displayMetrics.density
        assertTrue("$name must have a reachable 44dp touch target", control.visibleBounds.height() >= minimum)
    }

    private fun scrollToTop() {
        refreshUi()
        val scrollable = UiScrollable(UiSelector().scrollable(true))
        if (scrollable.exists()) scrollable.scrollToBeginning(12)
        refreshUi()
    }

    private fun scrollIntoViewIfAvailable(selector: UiSelector) {
        refreshUi()
        val scrollable = UiScrollable(UiSelector().scrollable(true))
        if (scrollable.exists()) scrollable.scrollIntoView(selector)
        refreshUi()
    }

    private fun refreshUi() {
        instrumentation.waitForIdleSync()
        device.waitForIdle()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            // API 33+ can retain stale Compose bounds after scrolling. Always
            // query a fresh tree before acting on a newly positioned control.
            instrumentation.uiAutomation.clearCache()
        }
    }

    private fun accessibilityNode(name: String): AccessibilityNodeInfo? {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) instrumentation.uiAutomation.clearCache()
        fun find(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
            if (node == null) return null
            if (node.viewIdResourceName == name) return node
            for (index in 0 until node.childCount) {
                find(node.getChild(index))?.let { return it }
            }
            return null
        }
        return find(instrumentation.uiAutomation.rootInActiveWindow)
    }

    private fun screenshot(name: String) {
        refreshUi()
        screenshotNow(name)
    }

    private fun screenshotNow(name: String) {
        val directory = File(context.getExternalFilesDir(null), "setup-refinement").apply { mkdirs() }
        assertTrue("Screenshot was not saved", device.takeScreenshot(File(directory, "$name.png")))
    }

    private fun assertExternalView(url: String, expectedCount: Int) {
        val deadline = android.os.SystemClock.elapsedRealtime() + TIMEOUT
        while (synchronized(externalViews) { externalViews.size } < expectedCount &&
            android.os.SystemClock.elapsedRealtime() < deadline) {
            android.os.SystemClock.sleep(50)
        }
        val intents = synchronized(externalViews) { externalViews.toList() }
        assertEquals("A project link must launch exactly one blocked intent", expectedCount, intents.size)
        assertEquals(Intent.ACTION_VIEW, intents.last().action)
        assertEquals(url, intents.last().dataString)
        assertEquals("The external link must not leave the isolated app", context.packageName, device.currentPackageName)
    }

    private fun recreateResumed(type: Class<out Activity>) {
        val previous = createdCount(type)
        instrumentation.runOnMainSync { resumedActivities().single { type.isInstance(it) }.recreate() }
        val deadline = android.os.SystemClock.elapsedRealtime() + TIMEOUT
        while (createdCount(type) == previous && android.os.SystemClock.elapsedRealtime() < deadline) {
            android.os.SystemClock.sleep(50)
        }
        awaitActivity(type)
        assertEquals("Recreation must create only one replacement", previous + 1, createdCount(type))
    }

    private fun awaitActivity(type: Class<out Activity>) {
        val deadline = android.os.SystemClock.elapsedRealtime() + TIMEOUT
        var resumed = false
        while (!resumed && android.os.SystemClock.elapsedRealtime() < deadline) {
            instrumentation.runOnMainSync {
                resumed = resumedActivities().singleOrNull()?.let { type.isInstance(it) } == true
            }
            if (!resumed) android.os.SystemClock.sleep(50)
        }
        assertTrue("Expected ${type.simpleName} to be resumed", resumed)
        refreshUi()
    }

    private fun assertRemains(type: Class<out Activity>) {
        awaitActivity(type)
        val countBefore = createdCount(type)
        // Observe several 100ms helper polls; a transient initial frame alone
        // must not pass a test whose requirement is to stay on this screen.
        val deadline = android.os.SystemClock.elapsedRealtime() + 700L
        do {
            instrumentation.runOnMainSync {
                val resumed = resumedActivities()
                assertEquals("Exactly one app Activity must be resumed", 1, resumed.size)
                assertTrue("Onboarding unexpectedly left ${type.simpleName}", type.isInstance(resumed.single()))
            }
            android.os.SystemClock.sleep(50)
        } while (android.os.SystemClock.elapsedRealtime() < deadline)
        assertEquals("${type.simpleName} must not repeatedly relaunch", countBefore, createdCount(type))
    }

    private fun createdCount(type: Class<out Activity>): Int = synchronized(createdActivities) {
        createdActivities.count { type.isInstance(it) }
    }

    // Read on the main thread, as required by the lifecycle monitor.
    private fun resumedActivities(): List<Activity> =
        ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED)
            .filter { it.packageName == context.packageName }

    private fun closeResumedActivity() {
        instrumentation.runOnMainSync {
            ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED)
                .toList().filter { it.packageName == context.packageName }.forEach { it.finish() }
        }
        instrumentation.waitForIdleSync()
    }

    private fun restore(prefs: SharedPreferences, values: Map<String, *>) {
        val edit = prefs.edit().clear()
        values.forEach { (key, value) ->
            when (value) {
                is String -> edit.putString(key, value)
                is Boolean -> edit.putBoolean(key, value)
                is Int -> edit.putInt(key, value)
                is Long -> edit.putLong(key, value)
                is Float -> edit.putFloat(key, value)
                is Set<*> -> {
                    @Suppress("UNCHECKED_CAST")
                    edit.putStringSet(key, value as Set<String>)
                }
            }
        }
        assertTrue("Could not restore isolated preferences", edit.commit())
    }

    companion object {
        private const val TIMEOUT = 6000L
        private val SETUP_FIELDS = setOf("setup-bank", "setup-primary-sim")
        private val PHONE_PERMISSIONS = listOf(
            android.Manifest.permission.CALL_PHONE,
            android.Manifest.permission.READ_PHONE_STATE,
            android.Manifest.permission.ANSWER_PHONE_CALLS
        )
    }
}
