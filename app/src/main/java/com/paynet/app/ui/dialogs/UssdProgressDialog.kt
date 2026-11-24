// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.ui.dialogs

import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.paynet.app.R
import kotlinx.coroutines.delay

@Composable
fun UssdProgressDialog(
    isVisible: Boolean,
    progressMessage: String = stringResource(R.string.ussd_dlg_initializing),
    showConfigurationOptions: Boolean = false,
    onConfigured: () -> Unit = {},
    onNotConfigured: () -> Unit = {},
    onDismiss: () -> Unit = {},
    onDoesNotWork: () -> Unit = {}
) {
    if (isVisible) {
        var showShortcuts by remember { mutableStateOf(false) }
        LaunchedEffect(Unit) {
            delay(3000)
            showShortcuts = true
        }
        OnboardingDialog(
            copy = OnboardingDialogCopy(
                title = stringResource(
                    if (showConfigurationOptions) {
                        R.string.onboarding_scan_confirm_title
                    } else {
                        R.string.onboarding_scan_progress_title
                    }
                ),
                message = stringResource(
                    if (showConfigurationOptions) {
                        R.string.onboarding_scan_confirm_message
                    } else {
                        R.string.onboarding_scan_progress_message
                    }
                )
            ),
            onDismiss = onDismiss,
            modifier = Modifier.testTag("ussd-dialog"),
            content = {
                if (!showConfigurationOptions) OnboardingDialogProgress(progressMessage)
            },
            actions = {
                UssdSetupActions(showConfigurationOptions, showShortcuts, onConfigured, onNotConfigured, onDoesNotWork)
            }
        )
    }
}

@Composable
private fun UssdSetupActions(
    showConfigurationOptions: Boolean,
    showShortcuts: Boolean,
    onConfigured: () -> Unit,
    onNotConfigured: () -> Unit,
    onDoesNotWork: () -> Unit
) {
    if (showConfigurationOptions) {
        OnboardingConfirmationActions(onConfigured, onNotConfigured, "ussd")
    } else if (showShortcuts) {
        OnboardingDialogAction(
            text = stringResource(R.string.onboarding_already_ready),
            onClick = onConfigured,
            modifier = Modifier.testTag("ussd-already-configured")
        )
        Spacer(modifier = Modifier.height(4.dp))
        OnboardingDialogAction(
            text = stringResource(R.string.onboarding_does_not_work),
            onClick = onDoesNotWork,
            secondary = true,
            modifier = Modifier.testTag("ussd-does-not-work")
        )
    }
}
