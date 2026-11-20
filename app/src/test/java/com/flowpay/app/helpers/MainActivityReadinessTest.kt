// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.flowpay.app.helpers

import android.app.Application
import android.content.Context
import android.content.ContextWrapper
import android.content.Intent
import android.content.res.Resources
import com.flowpay.app.R
import com.flowpay.app.data.TestResults
import com.flowpay.app.data.TestResultsManager
import com.flowpay.app.states.PaymentState
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/** Exercise fresh method gates without constructing telephony or permission managers. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = Application::class)
class MainActivityReadinessTest {
    private val application: Application = RuntimeEnvironment.getApplication()
    private val context: Context = object : ContextWrapper(application) {
        // These tests assert which message is selected, without loading app UI resources.
        private val strings = object : Resources(
            application.assets,
            application.resources.displayMetrics,
            application.resources.configuration
        ) {
            override fun getString(id: Int): String = id.toString()
        }
        override fun getResources(): Resources = strings
    }
    private val preferences = context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE)
    private val results = TestResultsManager(context)

    @Before
    fun reset() {
        preferences.edit().clear().putString("selected_primary_sim", "airtel").commit()
        context.getSharedPreferences("flowpay_test_results", Context.MODE_PRIVATE).edit().clear().commit()
        context.deleteDatabase("flowpay_database")
    }

    @After
    fun cleanup() = reset()

    @Test
    fun missingOrFalseReadinessRoutesBothActionsBeforePermissionRequests() {
        for (stored in listOf(null, TestResults())) {
            results.clearTestResults()
            stored?.let(results::saveTestResults)
            val callback = RecordingCallback()
            val helper = MainActivityHelper(context, callback)

            helper.initiateTransfer("9876543210", "1")
            helper.startQRScanning()

            assertEquals(2, callback.configurationRequests)
            assertNoNativeActions(callback)
            assertTrue(callback.messages.isEmpty())
        }
    }

    @Test
    fun contactReadinessCannotAuthorizeTheQrRail() {
        results.saveTestResults(TestResults(ussdEnabled = false, upi123Enabled = true))
        val callback = RecordingCallback()

        MainActivityHelper(context, callback).startQRScanning()

        assertEquals(1, callback.configurationRequests)
        assertNoNativeActions(callback)
    }

    @Test
    fun qrReadinessCannotAuthorizeTheContactRail() {
        results.saveTestResults(TestResults(ussdEnabled = true, upi123Enabled = false))
        val callback = RecordingCallback()

        MainActivityHelper(context, callback).initiateTransfer("9876543210", "1")

        assertEquals(1, callback.configurationRequests)
        assertNoNativeActions(callback)
    }

    @Test
    fun validReadinessReachesOnlyTheExistingPermissionGateWithoutInitializingManagers() {
        results.saveTestResults(TestResults(ussdEnabled = true, upi123Enabled = true))
        val callback = RecordingCallback()
        val helper = MainActivityHelper(context, callback)

        helper.initiateTransfer("9876543210", "1")
        helper.startQRScanning()

        assertEquals(0, callback.configurationRequests)
        assertEquals(2, callback.permissionRequests)
        assertEquals(0, callback.overlayRequests)
        assertEquals(0, callback.scannerRequests)
        assertTrue(callback.paymentStates.isEmpty())
    }

    @Test
    fun invalidContactInputKeepsValidationAheadOfTheReadinessGate() {
        val callback = RecordingCallback()
        val helper = MainActivityHelper(context, callback)

        helper.initiateTransfer("", "1")
        helper.initiateTransfer("123", "1")
        helper.initiateTransfer("9876543210", "0")

        assertEquals(
            listOf(
                context.getString(R.string.error_enter_phone_and_amount),
                context.getString(R.string.error_invalid_phone_number),
                context.getString(R.string.error_invalid_amount)
            ),
            callback.messages
        )
        assertEquals(0, callback.configurationRequests)
        assertNoNativeActions(callback)
    }

    @Test
    fun carrierRestrictionKeepsItsMessageAheadOfQrReadiness() {
        preferences.edit().putString("selected_primary_sim", "jio").commit()
        val callback = RecordingCallback()

        MainActivityHelper(context, callback).startQRScanning()

        assertEquals(listOf(SetupHelper.getScanToPayBlockedMessage(context)), callback.messages)
        assertEquals(0, callback.configurationRequests)
        assertNoNativeActions(callback)
    }

    @Test
    fun theSameHelperRechecksInvalidatedResultsAndPreservesUnrelatedState() {
        preferences.edit().putString("selected_bank", "sbi")
            .putBoolean("setup_completed", true).putBoolean("test_configuration_completed", true)
            .putBoolean(OnboardingFlow.APPEARANCE_COMPLETED, true)
            .putBoolean(OnboardingFlow.WELCOME_COMPLETED, true)
            .putBoolean("home_classic", true).putBoolean("home_monochrome", false).commit()
        context.openOrCreateDatabase("flowpay_database", Context.MODE_PRIVATE, null).use { database ->
            database.execSQL("CREATE TABLE transactions (transactionId TEXT, amount TEXT)")
            database.execSQL("INSERT INTO transactions VALUES ('existing-payment', '125')")
        }
        results.saveTestResults(TestResults(ussdEnabled = true, upi123Enabled = true))
        val allowed = RecordingCallback()
        val helper = MainActivityHelper(context, allowed)
        helper.startQRScanning()
        assertEquals(1, allowed.permissionRequests)

        SetupHelper.invalidatePaymentConfiguration(context)
        helper.initiateTransfer("9876543210", "1")
        helper.startQRScanning()

        assertEquals(2, allowed.configurationRequests)
        assertEquals("Invalidation must block before any additional permission request", 1, allowed.permissionRequests)
        assertEquals(0, allowed.overlayRequests)
        assertEquals(0, allowed.scannerRequests)
        assertTrue(allowed.paymentStates.isEmpty())
        assertNull(results.getTestResults())
        assertFalse(preferences.getBoolean("test_configuration_completed", true))
        assertPreservedSetupAndHistory()
    }

    private fun assertPreservedSetupAndHistory() {
        assertEquals("sbi", preferences.getString("selected_bank", null))
        assertEquals("airtel", preferences.getString("selected_primary_sim", null))
        assertTrue(preferences.getBoolean("setup_completed", false))
        assertTrue(preferences.getBoolean(OnboardingFlow.APPEARANCE_COMPLETED, false))
        assertTrue(preferences.getBoolean(OnboardingFlow.WELCOME_COMPLETED, false))
        assertTrue(preferences.getBoolean("home_classic", false))
        assertFalse(preferences.getBoolean("home_monochrome", true))
        context.openOrCreateDatabase("flowpay_database", Context.MODE_PRIVATE, null).use { database ->
            database.rawQuery("SELECT transactionId, amount FROM transactions", null).use { rows ->
                assertTrue(rows.moveToFirst())
                assertEquals("existing-payment", rows.getString(0))
                assertEquals("125", rows.getString(1))
                assertFalse(rows.moveToNext())
            }
        }
    }

    private fun assertNoNativeActions(callback: RecordingCallback) {
        assertEquals(0, callback.permissionRequests)
        assertEquals(0, callback.overlayRequests)
        assertEquals(0, callback.scannerRequests)
        assertTrue(callback.paymentStates.isEmpty())
    }

    private class RecordingCallback : MainActivityHelper.UICallback {
        var configurationRequests = 0
        var permissionRequests = 0
        var overlayRequests = 0
        var scannerRequests = 0
        val messages = mutableListOf<String>()
        val paymentStates = mutableListOf<PaymentState>()
        override fun showToast(message: String) { messages += message }
        override fun updatePaymentState(paymentState: PaymentState) { paymentStates += paymentState }
        override fun navigateToTestConfiguration() { configurationRequests++ }
        override fun requestPhonePermissions() { permissionRequests++ }
        override fun showOverlayPermissionExplanation() { overlayRequests++ }
        override fun launchQRScanner(intent: Intent) { scannerRequests++ }
        override fun navigateToSetup() = error("Unexpected setup navigation")
        override fun finishActivity() = error("Unexpected finish request")
    }
}
