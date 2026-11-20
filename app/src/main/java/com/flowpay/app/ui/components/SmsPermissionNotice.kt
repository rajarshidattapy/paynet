// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.ui.components

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.core.content.ContextCompat
import com.flowpay.app.R

/** Explains the limited SMS access before Android asks for consent. */
@Composable
fun SmsPermissionNotice() {
    val context = LocalContext.current
    var dismissed by remember { mutableStateOf(false) }
    var granted by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.RECEIVE_SMS) ==
                PackageManager.PERMISSION_GRANTED
        )
    }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        granted = it[Manifest.permission.RECEIVE_SMS] == true
        dismissed = true
    }
    if (!granted && !dismissed) {
        AlertDialog(
            onDismissRequest = { dismissed = true },
            title = { Text(stringResource(R.string.sms_permission_title)) },
            text = { Text(stringResource(R.string.sms_permission_explanation)) },
            confirmButton = {
                TextButton(onClick = {
                    launcher.launch(
                        if (Build.VERSION.SDK_INT >= 33) {
                            arrayOf(Manifest.permission.RECEIVE_SMS, Manifest.permission.POST_NOTIFICATIONS)
                        } else { arrayOf(Manifest.permission.RECEIVE_SMS) }
                    )
                }) { Text(stringResource(R.string.sms_permission_allow)) }
            },
            dismissButton = {
                TextButton(onClick = { dismissed = true }) {
                    Text(stringResource(R.string.sms_permission_later))
                }
            }
        )
    }
}
