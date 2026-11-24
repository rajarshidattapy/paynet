// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app

import android.animation.ValueAnimator
import android.app.Activity
import android.app.ActivityOptions
import android.content.Context
import android.os.Bundle
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import com.paynet.app.helpers.SetupHelper
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.delay
import kotlinx.coroutines.yield

private const val SETUP_SETTLE_MS = 600L

internal data class SetupAdvanceState(
    val selection: SetupHelper.SetupData,
    val complete: Boolean,
    val allowed: Boolean,
    val advanced: Boolean,
    val editing: Boolean
) {
    fun canProceed(): Boolean {
        if (!complete || !allowed) return false
        return !advanced && !editing
    }
}

@Composable
internal fun SetupAutoAdvance(
    state: SetupAdvanceState,
    readCurrent: () -> SetupAdvanceState,
    onAdvance: (SetupHelper.SetupData) -> Unit
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val currentState by rememberUpdatedState(readCurrent)
    val advance by rememberUpdatedState(onAdvance)
    LaunchedEffect(state, lifecycleOwner) {
        lifecycleOwner.lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            if (state.canProceed()) {
                if (ValueAnimator.areAnimatorsEnabled()) delay(SETUP_SETTLE_MS) else yield()
                val current = currentState()
                if (current.canProceed() && state.selection == current.selection &&
                    canLeaveSetup(context, lifecycleOwner.lifecycle)
                ) {
                    advance(state.selection)
                }
            }
            awaitCancellation()
        }
    }
}

internal fun setupSelectionComplete(selection: SetupHelper.SetupData, helper: SetupHelper): Boolean {
    val validBank = helper.getBanks().any { it.first == selection.selectedBank }
    val validPrimary = helper.getSimCarriers().any { it.first == selection.selectedPrimarySim }
    val validAccounts = validBank && validPrimary
    return selection.disclaimerAccepted && validAccounts
}

private fun canLeaveSetup(context: Context, lifecycle: Lifecycle): Boolean {
    val activity = context as? Activity
    val leaving = activity?.isFinishing == true || activity?.isDestroyed == true
    return !leaving && lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)
}

internal fun setupTransitionOptions(context: Context, backwards: Boolean = false): Bundle {
    // Keep both pages moving together, with a mirrored direction when reviewing setup.
    val animationsEnabled = ValueAnimator.areAnimatorsEnabled()
    val enter = when {
        !animationsEnabled -> 0
        backwards -> R.anim.setup_page_return_enter
        else -> R.anim.setup_page_enter
    }
    val exit = when {
        !animationsEnabled -> 0
        backwards -> R.anim.setup_page_return_exit
        else -> R.anim.setup_page_exit
    }
    return ActivityOptions.makeCustomAnimation(context, enter, exit).toBundle()
}
