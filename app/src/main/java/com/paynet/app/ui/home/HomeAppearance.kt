// SPDX-License-Identifier: Apache-2.0
package com.paynet.app.ui.home

import android.content.Context
import android.content.SharedPreferences
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext

/** Home layout preference and shared app-wide colour preference. */
data class HomeAppearance(
    val classic: Boolean = false,
    val monochrome: Boolean = !classic
) {
    fun save(context: Context) {
        context.getSharedPreferences("PayNetPrefs", Context.MODE_PRIVATE).edit()
            .putBoolean("home_classic", classic)
            .putBoolean("home_monochrome", monochrome)
            .remove("home_blood_red").apply()
    }
    companion object {
        fun read(context: Context): HomeAppearance {
            val prefs = context.getSharedPreferences("PayNetPrefs", Context.MODE_PRIVATE)
            val classic = prefs.getBoolean("home_classic", false)
            return HomeAppearance(
                classic = classic,
                monochrome = prefs.getBoolean("home_monochrome", !classic)
            )
        }
    }
}

@Composable
fun rememberHomeAppearance(): State<HomeAppearance> {
    val context = LocalContext.current
    val prefs = remember(context) { context.getSharedPreferences("PayNetPrefs", Context.MODE_PRIVATE) }
    val state = remember(prefs) { mutableStateOf(HomeAppearance.read(context)) }
    DisposableEffect(prefs) {
        val listener = SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
            if (key == null || key in listOf("home_classic", "home_monochrome")) {
                state.value = HomeAppearance.read(context)
            }
        }
        prefs.registerOnSharedPreferenceChangeListener(listener)
        onDispose { prefs.unregisterOnSharedPreferenceChangeListener(listener) }
    }
    return state
}
