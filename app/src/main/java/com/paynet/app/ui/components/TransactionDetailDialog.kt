// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.ui.components

import android.animation.ValueAnimator
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.outlined.AlternateEmail
import androidx.compose.material.icons.outlined.Payments
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.Phone
import androidx.compose.material.icons.outlined.ReceiptLong
import androidx.compose.material.icons.outlined.Schedule
import androidx.compose.material.icons.outlined.Tag
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.window.DialogWindowProvider
import com.paynet.app.OnboardingPage
import com.paynet.app.R
import com.paynet.app.data.Transaction
import com.paynet.app.ui.dialogs.OnboardingDialog
import com.paynet.app.ui.dialogs.OnboardingDialogAction
import com.paynet.app.ui.dialogs.OnboardingDialogCopy
import com.paynet.app.ui.theme.PayNetOnboardingSecondary
import com.paynet.app.ui.theme.PayNetOnboardingSurface
import com.paynet.app.ui.theme.PayNetStatusError
import com.paynet.app.ui.theme.LocalPayNetAccentTheme
import com.paynet.app.utils.CurrencyFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun TransactionDetailDialog(
    transaction: Transaction,
    onDismiss: () -> Unit,
    onDelete: (() -> Unit)? = null
) {
    val accent = LocalPayNetAccentTheme.current
    val clipboardManager = LocalClipboardManager.current
    val dialogDensity = LocalDensity.current
    var showDeleteConfirm by remember(transaction.transactionId) { mutableStateOf(false) }

    if (showDeleteConfirm && onDelete != null) {
        DeleteTransactionDialog(
            onCancel = { showDeleteConfirm = false },
            onDelete = {
                showDeleteConfirm = false
                onDelete()
            }
        )
        return
    }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)
    ) {
        ReceiptWindowMotion()
        CompositionLocalProvider(LocalDensity provides dialogDensity) {
            Box(
                Modifier.fillMaxSize().background(Color.Black).semantics {
                    testTagsAsResourceId = true
                }.testTag("transaction-detail-dialog")
            ) {
                OnboardingPage("transaction-detail-content", "transaction-detail-stack") {
                    Icon(
                        Icons.Outlined.ReceiptLong,
                        contentDescription = null,
                        tint = accent.primary,
                        modifier = Modifier.size(48.dp).testTag("transaction-detail-icon")
                    )
                    Spacer(Modifier.height(16.dp))
                    Text(
                        stringResource(R.string.detail_title),
                        color = Color.White,
                        fontSize = 31.sp,
                        lineHeight = 37.sp,
                        fontWeight = FontWeight.SemiBold,
                        textAlign = TextAlign.Center
                    )
                    Spacer(Modifier.height(28.dp))

                    val details = buildList {
                        add(
                            ReceiptField(
                                stringResource(R.string.detail_label_recipient),
                                transaction.recipientLabel
                                    ?: stringResource(R.string.detail_recipient_unknown),
                                Icons.Outlined.Person
                            )
                        )
                        // Unknown amounts stay absent, rather than becoming a lone currency symbol.
                        if (transaction.amount.isNotBlank()) {
                            add(
                                ReceiptField(
                                    stringResource(R.string.detail_amount),
                                    stringResource(R.string.amount_rupees, CurrencyFormat.inr(transaction.amount)),
                                    Icons.Outlined.Payments
                                )
                            )
                        }
                        transaction.phoneNumber?.takeIf { it.isNotBlank() }?.let {
                            add(
                                ReceiptField(
                                    stringResource(R.string.detail_label_phone_number),
                                    it,
                                    Icons.Outlined.Phone
                                )
                            )
                        }
                        transaction.upiId?.takeIf { it.isNotBlank() }?.let {
                            add(ReceiptField(stringResource(R.string.label_upi_id), it, Icons.Outlined.AlternateEmail))
                        }
                        transaction.bankRef?.takeIf { it.isNotBlank() }?.let {
                            add(ReceiptField(stringResource(R.string.label_bank_reference), it, Icons.Outlined.Tag))
                        }
                        add(
                            ReceiptField(
                                stringResource(R.string.label_date_time),
                                formatFullDate(transaction.timestamp),
                                Icons.Outlined.Schedule
                            )
                        )
                    }
                    Column(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(PayNetOnboardingSurface)
                    ) {
                        details.forEachIndexed { index, field ->
                            DetailRow(field) { clipboardManager.setText(AnnotatedString(field.value)) }
                            if (index < details.lastIndex) {
                                HorizontalDivider(
                                    Modifier.padding(start = 52.dp),
                                    thickness = 0.5.dp,
                                    color = Color.White.copy(alpha = 0.10f)
                                )
                            }
                        }
                    }
                    Spacer(Modifier.height(24.dp))
                    OnboardingDialogAction(
                        text = stringResource(R.string.detail_done),
                        onClick = onDismiss,
                        modifier = Modifier.testTag("transaction-detail-done")
                    )
                    if (onDelete != null) {
                        Spacer(Modifier.height(4.dp))
                        TextButton(
                            onClick = { showDeleteConfirm = true },
                            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                                .testTag("transaction-detail-delete")
                        ) {
                            Text(
                                stringResource(R.string.detail_delete_record),
                                color = PayNetStatusError,
                                fontSize = 14.sp
                            )
                        }
                    }
                }
                IconButton(
                    onClick = onDismiss,
                    modifier = Modifier.align(Alignment.TopStart).statusBarsPadding()
                        .padding(start = 12.dp, top = 8.dp).size(48.dp)
                ) {
                    Icon(
                        Icons.AutoMirrored.Filled.ArrowBack,
                        contentDescription = stringResource(R.string.detail_close),
                        tint = accent.accent,
                        modifier = Modifier.size(20.dp)
                    )
                }
            }
        }
    }
}

private data class ReceiptField(
    val label: String,
    val value: String,
    val icon: ImageVector,
    val valueColor: Color = PayNetOnboardingSecondary
)

@Composable
private fun DetailRow(field: ReceiptField, onCopy: () -> Unit) {
    val accent = LocalPayNetAccentTheme.current
    Row(
        modifier = Modifier.fillMaxWidth().heightIn(min = 76.dp).padding(horizontal = 18.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(field.icon, contentDescription = null, tint = accent.primary, modifier = Modifier.size(22.dp))
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(field.label, fontSize = 17.sp, fontWeight = FontWeight.Medium, color = Color.White)
            Spacer(Modifier.height(4.dp))
            Text(field.value, fontSize = 13.sp, lineHeight = 18.sp, color = field.valueColor)
        }
        Spacer(Modifier.width(8.dp))
        IconButton(onClick = onCopy, modifier = Modifier.size(48.dp)) {
            Icon(
                Icons.Default.ContentCopy,
                contentDescription = stringResource(R.string.detail_copy_field, field.label),
                modifier = Modifier.size(18.dp),
                tint = PayNetOnboardingSecondary
            )
        }
    }
}

@Composable
private fun DeleteTransactionDialog(onCancel: () -> Unit, onDelete: () -> Unit) {
    OnboardingDialog(
        copy = OnboardingDialogCopy(
            stringResource(R.string.detail_delete_confirm_title),
            stringResource(R.string.detail_delete_explanation)
        ),
        onDismiss = onCancel,
        modifier = Modifier.testTag("transaction-delete-dialog"),
        actions = {
            TextButton(
                onClick = onDelete,
                modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
            ) {
                Text(stringResource(R.string.detail_delete_record), color = PayNetStatusError, fontSize = 16.sp)
            }
            OnboardingDialogAction(
                stringResource(R.string.action_cancel),
                onCancel,
                modifier = Modifier.testTag("transaction-delete-cancel")
            )
        }
    )
}

private fun formatFullDate(timestamp: Long): String =
    SimpleDateFormat("dd MMM yyyy · h:mm a", Locale("en", "IN")).format(Date(timestamp))

/** Native window motion keeps the receipt and its background moving as one surface. */
@Composable
private fun ReceiptWindowMotion() {
    val view = LocalView.current
    SideEffect {
        (view.parent as? DialogWindowProvider)?.window?.setWindowAnimations(
            if (ValueAnimator.areAnimatorsEnabled()) R.style.PayNetReceiptMotion else 0
        )
    }
}
