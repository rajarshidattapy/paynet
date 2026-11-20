// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.flowpay.app.helpers

import android.app.Activity
import android.app.ActivityOptions
import android.content.Context
import android.content.Intent
import com.flowpay.app.AppearanceSetupActivity
import com.flowpay.app.MainActivity
import com.flowpay.app.ui.home.HomeAppearance

/** Appearance is a one-time introduction, independent of bank/SIM checks. */
object OnboardingFlow {
    const val APPEARANCE_COMPLETED = "appearance_setup_completed"
    const val WELCOME_COMPLETED = "welcome_completed"

    fun needsAppearance(context: Context): Boolean {
        val preferences = context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE)
        return !preferences.getBoolean(APPEARANCE_COMPLETED, false) ||
            !preferences.getBoolean(WELCOME_COMPLETED, false)
    }

    fun hasChosenAppearance(context: Context): Boolean =
        context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE)
            .getBoolean(APPEARANCE_COMPLETED, false)

    fun chooseAppearance(context: Context, classic: Boolean) {
        HomeAppearance(classic = classic).save(context)
        context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE).edit()
            .putBoolean(APPEARANCE_COMPLETED, true)
            .putBoolean(WELCOME_COMPLETED, false)
            .apply()
    }

    fun reviewAppearance(context: Context) {
        context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE).edit()
            .putBoolean(APPEARANCE_COMPLETED, false)
            .putBoolean(WELCOME_COMPLETED, false)
            .apply()
    }

    fun completeWelcome(context: Context) {
        context.getSharedPreferences("FlowpayPrefs", Context.MODE_PRIVATE).edit()
            .putBoolean(WELCOME_COMPLETED, true)
            .apply()
    }

    fun afterPayments(activity: Activity) {
        if (needsAppearance(activity)) openAppearance(activity) else openHome(activity)
    }

    fun openAppearance(activity: Activity) {
        activity.startActivity(Intent(activity, AppearanceSetupActivity::class.java))
        activity.finish()
    }

    fun openHome(activity: Activity) {
        val transition = ActivityOptions.makeCustomAnimation(
            activity,
            android.R.anim.fade_in,
            android.R.anim.fade_out
        )
        val intent = Intent(activity, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
        activity.startActivity(intent, transition.toBundle())
        activity.finish()
    }
}
