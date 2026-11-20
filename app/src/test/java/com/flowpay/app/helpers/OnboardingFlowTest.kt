// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.helpers

import android.app.Activity
import android.app.Application
import android.content.Context
import android.content.Intent
import com.flowpay.app.AppearanceSetupActivity
import com.flowpay.app.MainActivity
import com.flowpay.app.data.TestResults
import com.flowpay.app.data.TestResultsManager
import com.flowpay.app.ui.home.HomeAppearance
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = Application::class)
class OnboardingFlowTest {
    private val context: Context = RuntimeEnvironment.getApplication()
    private val preferences = context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE)
    private val resultPreferences = context.getSharedPreferences("flowpay_test_results", Context.MODE_PRIVATE)

    @Before
    fun reset() {
        preferences.edit().clear().commit()
        resultPreferences.edit().clear().commit()
    }

    @After
    fun cleanup() = reset()

    @Test
    fun bothChoiceAndWelcomeAreRequiredToFinishTheIntroduction() {
        for (chosen in listOf(false, true)) {
            for (welcomed in listOf(false, true)) {
                preferences.edit().putBoolean(OnboardingFlow.APPEARANCE_COMPLETED, chosen)
                    .putBoolean(OnboardingFlow.WELCOME_COMPLETED, welcomed).commit()
                assertEquals(chosen, OnboardingFlow.hasChosenAppearance(context))
                assertEquals(!(chosen && welcomed), OnboardingFlow.needsAppearance(context))
            }
        }
    }

    @Test
    fun choosingEitherLayoutSetsItsDefaultColorAndPreservesPaymentReadiness() {
        val ready = TestResults(ussdEnabled = true, upi123Enabled = true, timestamp = 123L)
        TestResultsManager(context).saveTestResults(ready)
        preferences.edit().putString("selected_bank", "sbi")
            .putBoolean("test_configuration_completed", true).commit()
        for (classic in listOf(false, true)) {
            val appearance = HomeAppearance(classic = !classic, monochrome = classic)
            appearance.save(context)
            OnboardingFlow.completeWelcome(context)

            OnboardingFlow.chooseAppearance(context, classic)

            assertEquals(HomeAppearance(classic = classic, monochrome = !classic), HomeAppearance.read(context))
            assertTrue(OnboardingFlow.hasChosenAppearance(context))
            assertTrue("The hello step must still run", OnboardingFlow.needsAppearance(context))
            assertFalse(preferences.getBoolean(OnboardingFlow.WELCOME_COMPLETED, true))
            assertEquals("sbi", preferences.getString("selected_bank", null))
            assertTrue(preferences.getBoolean("test_configuration_completed", false))
            assertEquals(ready, TestResultsManager(context).getTestResults())
        }
    }

    @Test
    fun reviewingAppearanceKeepsTheSavedLookWithoutFinishingWelcome() {
        val appearance = HomeAppearance(classic = true, monochrome = false)
        appearance.save(context)
        OnboardingFlow.chooseAppearance(context, classic = true)
        OnboardingFlow.completeWelcome(context)

        OnboardingFlow.reviewAppearance(context)

        assertEquals(appearance, HomeAppearance.read(context))
        assertFalse(OnboardingFlow.hasChosenAppearance(context))
        assertFalse(preferences.getBoolean(OnboardingFlow.WELCOME_COMPLETED, true))
        assertTrue(OnboardingFlow.needsAppearance(context))
    }

    @Test
    fun finishingWelcomeCannotStandInForAnExplicitChoice() {
        OnboardingFlow.completeWelcome(context)
        assertFalse(OnboardingFlow.hasChosenAppearance(context))
        assertTrue(OnboardingFlow.needsAppearance(context))
        assertFalse(preferences.getBoolean("setup_completed", false))
        assertFalse(preferences.getBoolean("test_configuration_completed", false))
        assertNull(TestResultsManager(context).getTestResults())
    }

    @Test
    fun paymentCompletionRoutesToTheUnfinishedIntroductionAndFinishesItsOrigin() {
        for ((chosen, welcomed) in listOf(false to false, true to false, false to true, true to true)) {
            preferences.edit().putBoolean(OnboardingFlow.APPEARANCE_COMPLETED, chosen)
                .putBoolean(OnboardingFlow.WELCOME_COMPLETED, welcomed).commit()
            val controller = Robolectric.buildActivity(Activity::class.java).setup()
            val activity = controller.get()

            OnboardingFlow.afterPayments(activity)

            val expected = if (chosen && welcomed) MainActivity::class.java else AppearanceSetupActivity::class.java
            val destination = shadowOf(activity).nextStartedActivity
            assertEquals(expected.name, destination.component?.className)
            if (expected == MainActivity::class.java) {
                assertTrue(
                    "Returning home must clear an older home and intermediate setup screens",
                    destination.flags and Intent.FLAG_ACTIVITY_CLEAR_TOP != 0
                )
            }
            assertTrue("The previous onboarding screen must leave the back stack", activity.isFinishing)
            assertNull("Routing must start only one destination", shadowOf(activity).nextStartedActivity)
            controller.pause().stop().destroy()
        }
    }
}
