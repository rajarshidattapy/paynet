// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.ui.dialogs

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.paynet.app.R
import com.paynet.app.ui.theme.PayNetOnboardingSurface
import com.paynet.app.ui.theme.PayNetTextLightGray
import com.paynet.app.ui.theme.LocalPayNetAccentTheme

@Composable
fun OnboardingDialog(
    copy: OnboardingDialogCopy,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit = {},
    actions: @Composable ColumnScope.() -> Unit
) {
    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(dismissOnClickOutside = false, usePlatformDefaultWidth = false)
    ) {
        Box(
            modifier = Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing).padding(24.dp),
            contentAlignment = Alignment.Center
        ) {
            Column(
                modifier = modifier
                    .widthIn(max = 400.dp)
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(24.dp))
                    .background(PayNetOnboardingSurface)
                    .semantics { testTagsAsResourceId = true }
                    .verticalScroll(rememberScrollState())
                    .padding(24.dp)
            ) {
                OnboardingDialogHeading(copy.title, onDismiss)
                copy.message?.let {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(it, color = PayNetTextLightGray, fontSize = 16.sp, lineHeight = 23.sp)
                }
                content()
                Spacer(modifier = Modifier.height(24.dp))
                actions()
            }
        }
    }
}

@Composable
private fun OnboardingDialogHeading(title: String, onDismiss: () -> Unit) {
    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
        Text(
            text = title,
            modifier = Modifier.weight(1f).padding(top = 8.dp),
            color = Color.White,
            fontSize = 24.sp,
            lineHeight = 29.sp,
            fontWeight = FontWeight.SemiBold
        )
        IconButton(
            onClick = onDismiss,
            modifier = Modifier.size(48.dp).testTag("onboarding-dialog-close")
        ) {
            Icon(
                Icons.Default.Close,
                contentDescription = stringResource(R.string.onboarding_dialog_close),
                tint = PayNetTextLightGray,
                modifier = Modifier.size(22.dp)
            )
        }
    }
}

@Composable
fun OnboardingDialogAction(
    text: String,
    onClick: () -> Unit,
    secondary: Boolean = false,
    modifier: Modifier = Modifier,
    enabled: Boolean = true
) {
    val accent = LocalPayNetAccentTheme.current
    val actionModifier = modifier.fillMaxWidth().heightIn(min = 48.dp)
    if (secondary) {
        TextButton(
            onClick = onClick,
            enabled = enabled,
            modifier = actionModifier,
            colors = ButtonDefaults.textButtonColors(contentColor = accent.accent)
        ) {
            Text(text, fontSize = 16.sp, textAlign = TextAlign.Center)
        }
    } else {
        Button(
            onClick = onClick,
            enabled = enabled,
            modifier = actionModifier,
            shape = RoundedCornerShape(14.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = accent.primaryDark,
                contentColor = accent.onPrimaryDark
            ),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp)
        ) {
            Text(text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center)
        }
    }
}

@Composable
internal fun OnboardingDialogProgress(message: String) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(top = 20.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        CircularProgressIndicator(
            modifier = Modifier.size(20.dp),
            color = LocalPayNetAccentTheme.current.accent,
            strokeWidth = 2.dp
        )
        Text(message, color = PayNetTextLightGray, fontSize = 14.sp, lineHeight = 20.sp)
    }
}

@Composable
internal fun OnboardingConfirmationActions(onConfigured: () -> Unit, onNotConfigured: () -> Unit, tagPrefix: String) {
    OnboardingDialogAction(
        text = stringResource(R.string.onboarding_confirm_ready),
        onClick = onConfigured,
        modifier = Modifier.testTag("$tagPrefix-configured")
    )
    Spacer(modifier = Modifier.height(4.dp))
    OnboardingDialogAction(
        text = stringResource(R.string.onboarding_not_yet),
        onClick = onNotConfigured,
        secondary = true,
        modifier = Modifier.testTag("$tagPrefix-not-configured")
    )
}
