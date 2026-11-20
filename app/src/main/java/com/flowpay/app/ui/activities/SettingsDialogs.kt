// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.flowpay.app.ui.activities

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.flowpay.app.R
import com.flowpay.app.ui.theme.FlowpayStatusError
import com.flowpay.app.ui.theme.FlowpayTextPale

@Composable
internal fun VersionDialog(onDismiss: () -> Unit) {
    val context = LocalContext.current
    SettingsSheet(stringResource(R.string.settings_official_title), onDismiss, "settings-version-dialog") {
        Text(
            stringResource(R.string.settings_official_message),
            color = FlowpayTextPale,
            fontSize = 15.sp,
            lineHeight = 22.sp
        )
        Spacer(Modifier.height(22.dp))
        SettingsChoiceGroup {
            SettingsSheetLink(stringResource(R.string.settings_github_action), "settings-github") {
                openSettingsLink(context, "https://github.com/Flowpayup/Payments-Without-Internet")
            }
        }
    }
}

@Composable
internal fun BankPickerDialog(
    selectedBank: Bank,
    onBankSelected: (Bank) -> Unit,
    onDismiss: () -> Unit
) {
    SettingsSheet(stringResource(R.string.settings_bank_title), onDismiss, "settings-bank-dialog") {
        SettingsChoiceGroup {
            banks.forEachIndexed { index, bank ->
                if (index > 0) SettingsChoiceDivider()
                SettingsChoice(
                    SettingsChoicePresentation("bank-" + bank.id, bank.name),
                    bank.id == selectedBank.id
                ) { onBankSelected(bank) }
            }
        }
    }
}

@Composable
internal fun SimPickerDialog(
    selectedSimId: String,
    onSimSelected: (String) -> Unit,
    onDismiss: () -> Unit
) {
    val sims = listOf("jio" to "Jio", "airtel" to "Airtel", "vodafone" to "Vodafone", "bsnl" to "BSNL")
    SettingsSheet(stringResource(R.string.settings_sim_title), onDismiss, "settings-sim-dialog") {
        SettingsChoiceGroup {
            sims.forEachIndexed { index, (id, name) ->
                if (index > 0) SettingsChoiceDivider()
                SettingsChoice(SettingsChoicePresentation("sim-$id", name), id == selectedSimId) { onSimSelected(id) }
            }
        }
    }
}

@Composable
internal fun ClearDataDialog(
    onDismiss: () -> Unit,
    onConfirm: () -> Unit,
    resetting: Boolean = false,
    failed: Boolean = false
) {
    SettingsSheet(
        stringResource(R.string.settings_reset_title),
        onDismiss,
        "settings-clear-dialog",
        dismissEnabled = !resetting
    ) {
        Text(
            stringResource(R.string.settings_refined_clear_message),
            color = FlowpayTextPale,
            fontSize = 15.sp,
            lineHeight = 22.sp
        )
        Spacer(Modifier.height(20.dp))
        if (failed) {
            Text(
                stringResource(R.string.polish_reset_failed),
                color = FlowpayStatusError,
                fontSize = 14.sp,
                lineHeight = 20.sp,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }.testTag("settings-reset-error")
            )
            Spacer(Modifier.height(12.dp))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TextButton(
                onClick = onDismiss,
                enabled = !resetting,
                modifier = Modifier.weight(1f).heightIn(min = 48.dp)
            ) {
                Text(stringResource(R.string.action_cancel), fontSize = 15.sp)
            }
            TextButton(
                onClick = onConfirm,
                enabled = !resetting,
                modifier = Modifier.weight(1f).heightIn(min = 48.dp).testTag("settings-confirm-clear"),
                colors = ButtonDefaults.textButtonColors(contentColor = FlowpayStatusError)
            ) {
                Text(
                    stringResource(if (resetting) R.string.polish_resetting else R.string.settings_reset_action),
                    fontSize = 15.sp,
                    fontWeight = FontWeight.SemiBold
                )
            }
        }
    }
}

private fun openSettingsLink(context: Context, link: String) {
    context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(link)))
}
