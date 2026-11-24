// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.ui.dialogs

import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import com.paynet.app.R
import kotlinx.coroutines.delay

@Composable
fun Upi123ProgressDialog(
    isVisible: Boolean,
    showConfigurationOptions: Boolean = false,
    onConfigured: () -> Unit = {},
    onNotConfigured: () -> Unit = {},
    onDismiss: () -> Unit = {}
) {
    if (isVisible) {
        var showAlreadySetUp by remember { mutableStateOf(false) }
        LaunchedEffect(Unit) {
            delay(3000)
            showAlreadySetUp = true
        }
        OnboardingDialog(
            copy = OnboardingDialogCopy(
                title = stringResource(
                    if (showConfigurationOptions) {
                        R.string.onboarding_contact_confirm_title
                    } else {
                        R.string.onboarding_contact_progress_title
                    }
                ),
                message = stringResource(
                    if (showConfigurationOptions) {
                        R.string.onboarding_contact_confirm_message
                    } else {
                        R.string.onboarding_contact_progress_message
                    }
                )
            ),
            onDismiss = onDismiss,
            modifier = Modifier.testTag("upi123-dialog"),
            content = {
                if (!showConfigurationOptions) {
                    OnboardingDialogProgress(stringResource(R.string.onboarding_contact_waiting))
                }
            },
            actions = {
                Upi123SetupActions(showConfigurationOptions, showAlreadySetUp, onConfigured, onNotConfigured)
            }
        )
    }
}

@Composable
private fun Upi123SetupActions(
    showConfigurationOptions: Boolean,
    showAlreadySetUp: Boolean,
    onConfigured: () -> Unit,
    onNotConfigured: () -> Unit
) {
    if (showConfigurationOptions) {
        OnboardingConfirmationActions(onConfigured, onNotConfigured, "upi123")
    } else if (showAlreadySetUp) {
        OnboardingDialogAction(
            text = stringResource(R.string.onboarding_already_ready),
            onClick = onConfigured,
            modifier = Modifier.testTag("upi123-already-configured")
        )
    }
}
