// SPDX-License-Identifier: Apache-2.0
package com.paynet.app.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.QrCode
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.nestedscroll.NestedScrollConnection
import androidx.compose.ui.input.nestedscroll.NestedScrollSource
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.Velocity
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.paynet.app.R
import com.paynet.app.data.PaymentDetails
import com.paynet.app.data.PaymentStatus
import com.paynet.app.formatDate
import com.paynet.app.ui.theme.HomeColors

private val scanSize = 62.dp
private val panelExtension = 32.dp
private val scanBottom = 36.dp + panelExtension
private val listBottomInset = 24.dp
private val lastRowClearance = scanBottom + scanSize - listBottomInset + 16.dp

private data class ModernHistoryState(
    val payments: List<PaymentDetails>,
    val loading: Boolean,
    val error: String?
)

/** A fixed history panel keeps the scan action at its original empty-state position. */
@Composable
@Suppress("LongParameterList")
internal fun ModernRecentPayments(
    payments: List<PaymentDetails>,
    loading: Boolean,
    error: String?,
    panelHeight: Dp,
    control: Color,
    ink: Color,
    scanState: String,
    scanEnabled: Boolean,
    onRetry: () -> Unit,
    onTransaction: (PaymentDetails) -> Unit,
    onHistory: () -> Unit,
    onScan: () -> Unit
) {
    val state = ModernHistoryState(payments, loading, error)
    Box(
        Modifier.fillMaxWidth().height(panelHeight + panelExtension).clip(RoundedCornerShape(28.dp))
            .background(HomeColors.modernHistory).testTag("home-recent-panel")
    ) {
        ModernHistoryListArea(state, control, onRetry, onTransaction, onHistory)
        if (!loading && error == null && payments.isEmpty()) {
            ModernHistoryEmpty(
                Modifier.matchParentSize().padding(top = 78.dp, bottom = scanBottom + scanSize + 28.dp)
            )
        }
        HomeAction(
            label = stringResource(R.string.home_scan_to_pay),
            icon = Icons.Default.QrCode,
            background = control,
            ink = ink,
            modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = scanBottom).size(scanSize)
                .testTag("home-floating-scan"),
            enabled = scanEnabled,
            state = scanState,
            round = true,
            iconSize = 30.dp,
            onClick = onScan
        )
    }
}

@Composable
private fun ModernHistoryListArea(
    state: ModernHistoryState,
    control: Color,
    onRetry: () -> Unit,
    onTransaction: (PaymentDetails) -> Unit,
    onHistory: () -> Unit
) {
    Column(
        Modifier.fillMaxSize().padding(
            start = 24.dp,
            end = 24.dp,
            top = 24.dp,
            bottom = listBottomInset
        )
    ) {
        ModernHistoryHeader(onHistory)
        Spacer(Modifier.height(10.dp))
        Box(Modifier.fillMaxWidth().weight(1f)) {
            ModernHistoryContent(state, control, onRetry, onTransaction)
        }
    }
}

@Composable
private fun ModernHistoryHeader(onHistory: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 44.dp).testTag("home-recent-header"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text(
            stringResource(R.string.home_recent),
            Modifier.weight(1f),
            color = HomeColors.historyText,
            fontSize = 20.sp,
            lineHeight = 26.sp,
            fontWeight = FontWeight.SemiBold,
            letterSpacing = (-.5).sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
        Box(
            Modifier.height(44.dp).clickable(role = Role.Button, onClick = onHistory).padding(start = 12.dp),
            contentAlignment = Alignment.Center
        ) {
            Text(
                stringResource(R.string.home_view_all),
                color = HomeColors.historyAction,
                fontSize = 12.5.sp,
                lineHeight = 20.sp
            )
        }
    }
}

@Composable
private fun ModernHistoryContent(
    state: ModernHistoryState,
    control: Color,
    onRetry: () -> Unit,
    onTransaction: (PaymentDetails) -> Unit
) {
    when {
        state.loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(Modifier.size(24.dp), color = control, strokeWidth = 2.dp)
        }
        state.error != null -> Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(vertical = 30.dp)
        ) {
            Text(stringResource(R.string.error_load_transactions), color = HomeColors.muted, fontSize = 14.sp)
            TextButton(onClick = onRetry) { Text(stringResource(R.string.home_retry), color = Color.White) }
        }
        state.payments.isEmpty() -> Unit
        else -> LazyColumn(
            modifier = Modifier.fillMaxSize().nestedScroll(remember { ContainedHistoryScroll() })
                .testTag("home-recent-list"),
            // The viewport continues behind QR; only the final row gets scrollable clearance.
            contentPadding = PaddingValues(bottom = lastRowClearance)
        ) {
            items(state.payments, key = { it.id }) { payment ->
                ModernPaymentRow(payment) { onTransaction(payment) }
            }
        }
    }
}

@Composable
private fun ModernPaymentRow(payment: PaymentDetails, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 90.dp).clip(RoundedCornerShape(14.dp))
            .clickable(role = Role.Button, onClick = onClick).padding(vertical = 16.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        ModernPaymentRecipient(payment, Modifier.weight(1f))
        ModernPaymentStatus(payment)
    }
}

@Composable
private fun ModernPaymentRecipient(payment: PaymentDetails, modifier: Modifier) {
    Column(modifier) {
        Text(
            payment.recipientLabel ?: stringResource(R.string.detail_recipient_unknown),
            color = HomeColors.historyText,
            fontSize = 17.sp,
            lineHeight = 24.sp,
            fontWeight = FontWeight.Medium,
            letterSpacing = (-.3).sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
        Spacer(Modifier.height(4.dp))
        Text(
            formatDate(payment.timestamp),
            color = HomeColors.historyMuted,
            fontSize = 13.sp,
            lineHeight = 18.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
    }
}

@Composable
private fun ModernPaymentStatus(payment: PaymentDetails) {
    val status = stringResource(
        when {
            payment.userConfirmed == true -> R.string.home_confirmed
            payment.userConfirmed == false -> R.string.home_not_confirmed
            payment.status == PaymentStatus.COMPLETED -> R.string.status_label_success
            payment.status == PaymentStatus.FAILED -> R.string.status_label_failed
            payment.status == PaymentStatus.PENDING -> R.string.home_pending
            else -> R.string.home_unverified
        }
    )
    Box(Modifier.size(26.dp), contentAlignment = Alignment.Center) {
        if (payment.userConfirmed == null) {
            Icon(painterResource(R.drawable.home_arrow), status, Modifier.size(16.dp), tint = HomeColors.historyMuted)
        } else {
            Icon(
                if (payment.userConfirmed == true) Icons.Default.Check else Icons.Default.Close,
                status,
                Modifier.size(16.dp),
                tint = HomeColors.historyMuted
            )
        }
    }
}

@Composable
private fun ModernHistoryEmpty(modifier: Modifier) {
    Box(modifier, contentAlignment = Alignment.BottomCenter) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Box(
                Modifier.size(52.dp).background(Color.White.copy(alpha = .05f), CircleShape),
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Default.History, null, Modifier.size(24.dp), tint = HomeColors.muted)
            }
            Spacer(Modifier.height(12.dp))
            Text(
                stringResource(R.string.home_empty),
                color = Color.White,
                fontSize = 16.sp,
                lineHeight = 24.sp,
                fontWeight = FontWeight.SemiBold
            )
        }
    }
}

/** Keep end-of-list drag and fling remainder from moving the surrounding home page. */
private class ContainedHistoryScroll : NestedScrollConnection {
    override fun onPostScroll(consumed: Offset, available: Offset, source: NestedScrollSource): Offset =
        Offset(0f, available.y)

    override suspend fun onPostFling(consumed: Velocity, available: Velocity): Velocity =
        Velocity(0f, available.y)
}
