// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.helpers

import android.app.Application
import android.content.Context
import com.paynet.app.setupSelectionComplete
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = Application::class)
class SetupSingleSimSelectionTest {
    private val context: Context = RuntimeEnvironment.getApplication()
    private val helper = SetupHelper(
        context,
        object : SetupHelper.UICallback {
            override fun showToast(message: String) = error("Unexpected message: $message")
            override fun navigateToTestConfiguration() = error("Validation must not navigate")
        }
    )
    private val selection = SetupHelper.SetupData("sbi", "airtel", false, "", true)

    @Test
    fun onlyTheVisibleBankCallingSimAndConsentDetermineCompletion() {
        for (dual in listOf(false, true)) {
            for (secondary in listOf("", "retired-carrier", "airtel", "vodafone")) {
                val legacy = selection.copy(isDualSimEnabled = dual, selectedSecondarySim = secondary)
                assertTrue(setupSelectionComplete(legacy, helper))
                assertTrue(helper.validateForm(legacy).isValid)
            }
        }
    }

    @Test
    fun hiddenLegacyChoicesCannotReplaceAValidVisibleSelectionOrExplicitConsent() {
        val legacy = selection.copy(isDualSimEnabled = true, selectedSecondarySim = "retired-carrier")
        val invalid = listOf(
            legacy.copy(selectedBank = ""),
            legacy.copy(selectedBank = "retired-bank"),
            legacy.copy(selectedPrimarySim = ""),
            legacy.copy(selectedPrimarySim = "retired-carrier"),
            legacy.copy(disclaimerAccepted = false)
        )
        for (incomplete in invalid) assertFalse(setupSelectionComplete(incomplete, helper))
        assertFalse(helper.validateForm(legacy.copy(disclaimerAccepted = false)).isValid)
    }
}
