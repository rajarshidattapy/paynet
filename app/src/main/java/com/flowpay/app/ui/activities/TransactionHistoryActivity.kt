// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.flowpay.app.ui.activities

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.flowpay.app.R
import com.flowpay.app.data.Transaction
import com.flowpay.app.ui.components.TransactionDetailDialog
import com.flowpay.app.ui.theme.FlowpayAccentProvider
import com.flowpay.app.ui.theme.FlowpayDarkGray
import com.flowpay.app.ui.theme.FlowpayMediumGray
import com.flowpay.app.ui.theme.FlowpayStatusError
import com.flowpay.app.ui.theme.FlowpayTextLightGray
import com.flowpay.app.ui.theme.FlowpayTheme
import com.flowpay.app.ui.theme.LocalFlowpayAccentTheme
import com.flowpay.app.ui.theme.statusColor
import com.flowpay.app.utils.CurrencyFormat
import com.flowpay.app.viewmodel.TransactionViewModel
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

// Utility functions
fun formatDate(timestamp: Long): String {
    val formatter = SimpleDateFormat("dd MMM, HH:mm", Locale("en", "IN"))
    return formatter.format(Date(timestamp))
}

fun formatTime(timestamp: Long): String {
    val formatter = SimpleDateFormat("hh:mm a", Locale("en", "IN"))
    return formatter.format(Date(timestamp))
}

@androidx.annotation.StringRes
fun statusLabelRes(status: String): Int = when (status.uppercase()) {
    "USER_CONFIRMED" -> R.string.manual_confirmed_label
    "USER_NOT_CONFIRMED" -> R.string.manual_not_confirmed_label
    "SUCCESS", "SUCCESSFUL", "COMPLETED" -> R.string.status_label_success
    "UNVERIFIED" -> R.string.status_label_unverified
    "NEEDS_REVIEW" -> R.string.status_label_needs_review
    "CANCELLED" -> R.string.status_label_cancelled
    "FAILED", "DECLINED" -> R.string.status_label_failed
    else -> R.string.status_label_pending
}

private fun isSameDay(c1: Calendar, c2: Calendar): Boolean =
    c1.get(Calendar.YEAR) == c2.get(Calendar.YEAR) &&
        c1.get(Calendar.DAY_OF_YEAR) == c2.get(Calendar.DAY_OF_YEAR)

class TransactionHistoryActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setTheme(R.style.Theme_Flowpay)
        setContent {
            FlowpayAccentProvider {
                FlowpayTheme {
                    TransactionHistoryScreen(
                        onBackClick = { finish() }
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TransactionHistoryScreen(
    onBackClick: () -> Unit
) {
    val transactionViewModel: TransactionViewModel = viewModel()

    // State
    var searchQuery by rememberSaveable { mutableStateOf("") }
    var showSearchBar by rememberSaveable { mutableStateOf(false) }
    var selectedTransaction by remember { mutableStateOf<Transaction?>(null) }

    val focusManager = LocalFocusManager.current
    val snackbar = remember { SnackbarHostState() }
    val actionError by transactionViewModel.error.collectAsState()
    LaunchedEffect(actionError) {
        actionError?.let {
            snackbar.showSnackbar(it)
            transactionViewModel.clearError()
        }
    }
    val history by transactionViewModel.historyState.collectAsState()
    LaunchedEffect(transactionViewModel) { transactionViewModel.loadHistory() }
    val allTransactions = history.transactions
    val isLoading = history.isLoading
    val error = history.error
    val filteredTransactions = remember(allTransactions, searchQuery) {
        allTransactions.filter { it.matchesSearch(searchQuery) }
    }

    // Group by date
    val groupToday = stringResource(R.string.history_group_today)
    val groupYesterday = stringResource(R.string.history_group_yesterday)
    val groupThisWeek = stringResource(R.string.history_group_this_week)
    val groupedTransactions = remember(filteredTransactions, groupToday, groupYesterday, groupThisWeek) {
        val today = Calendar.getInstance()
        val yesterday = Calendar.getInstance().apply { add(Calendar.DAY_OF_YEAR, -1) }
        val weekAgo = Calendar.getInstance().apply { add(Calendar.DAY_OF_YEAR, -7) }

        val grouped = linkedMapOf<String, List<Transaction>>()
        filteredTransactions
            .sortedByDescending { it.timestamp }
            .groupBy { transaction ->
                val txCal = Calendar.getInstance().apply { timeInMillis = transaction.timestamp }
                when {
                    isSameDay(txCal, today) -> groupToday
                    isSameDay(txCal, yesterday) -> groupYesterday
                    txCal.after(weekAgo) -> groupThisWeek
                    else -> historicalDateLabel(transaction.timestamp, today.timeInMillis)
                }
            }
            .forEach { (key, value) -> grouped[key] = value }
        grouped
    }

    val accent = LocalFlowpayAccentTheme.current

    Surface(
        modifier = Modifier.fillMaxSize().semantics { testTagsAsResourceId = true },
        color = Color.Black
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Color.Black)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .widthIn(max = 420.dp)
                    .align(Alignment.Center)
                    .background(Color.Black)
                    .statusBarsPadding()
                    .navigationBarsPadding()
            ) {
                Spacer(modifier = Modifier.height(8.dp))

                // ═══ COMPACT HEADER ═══
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 8.dp)
                        .clip(RoundedCornerShape(20.dp))
                        .background(
                            brush = Brush.verticalGradient(
                                colors = listOf(
                                    accent.headerGradientStart,
                                    accent.headerGradientEnd
                                )
                            )
                        )
                        .padding(horizontal = 16.dp, vertical = 16.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        IconButton(onClick = onBackClick, modifier = Modifier.size(48.dp)) {
                            Box(
                                Modifier.size(36.dp).clip(CircleShape)
                                    .background(Color.White.copy(alpha = 0.22f)),
                                contentAlignment = Alignment.Center
                            ) {
                                Icon(
                                    imageVector = Icons.Default.ArrowBack,
                                    contentDescription = stringResource(R.string.history_back),
                                    tint = accent.onAccent,
                                    modifier = Modifier.size(20.dp)
                                )
                            }
                        }

                        Spacer(modifier = Modifier.width(12.dp))

                        Text(
                            text = stringResource(R.string.history_title),
                            fontSize = 20.sp,
                            fontWeight = FontWeight.Bold,
                            color = accent.onAccent,
                            letterSpacing = 0.3.sp,
                            modifier = Modifier.weight(1f)
                        )

                        IconButton(
                            onClick = {
                                if (showSearchBar) {
                                    searchQuery = ""
                                    focusManager.clearFocus()
                                }
                                showSearchBar = !showSearchBar
                            },
                            modifier = Modifier.size(48.dp).testTag("history-search-toggle")
                        ) {
                            Box(
                                Modifier.size(36.dp).clip(CircleShape).background(
                                    Color.White.copy(alpha = if (showSearchBar) 0.35f else 0.22f)
                                ),
                                contentAlignment = Alignment.Center
                            ) {
                                Icon(
                                    imageVector = if (showSearchBar) Icons.Default.Close else Icons.Default.Search,
                                    contentDescription = stringResource(
                                        if (showSearchBar) R.string.history_close_search else R.string.history_search
                                    ),
                                    tint = accent.onAccent,
                                    modifier = Modifier.size(20.dp)
                                )
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))

                // ═══ SEARCH BAR ═══
                AnimatedVisibility(
                    visible = showSearchBar,
                    enter = fadeIn() + expandVertically(),
                    exit = fadeOut() + shrinkVertically()
                ) {
                    OutlinedTextField(
                        value = searchQuery,
                        onValueChange = { searchQuery = it },
                        placeholder = {
                            Text(
                                stringResource(R.string.history_search_placeholder),
                                color = FlowpayTextLightGray,
                                fontSize = 14.sp
                            )
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp)
                            .padding(bottom = 8.dp).testTag("history-search-field"),
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Search,
                                contentDescription = null,
                                tint = FlowpayTextLightGray,
                                modifier = Modifier.size(20.dp)
                            )
                        },
                        trailingIcon = {
                            if (searchQuery.isNotEmpty()) {
                                IconButton(onClick = { searchQuery = "" }) {
                                    Icon(
                                        imageVector = Icons.Default.Close,
                                        contentDescription = stringResource(R.string.history_clear_search),
                                        tint = FlowpayTextLightGray,
                                        modifier = Modifier.size(18.dp)
                                    )
                                }
                            }
                        },
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White,
                            focusedBorderColor = accent.primary,
                            unfocusedBorderColor = Color.Transparent,
                            focusedContainerColor = FlowpayDarkGray,
                            unfocusedContainerColor = FlowpayDarkGray
                        ),
                        shape = RoundedCornerShape(16.dp),
                        singleLine = true
                    )
                }

                // ═══ TRANSACTION LIST ═══
                when {
                    isLoading -> {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .weight(1f),
                            contentAlignment = Alignment.Center
                        ) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(32.dp),
                                color = accent.headerGradientStart,
                                strokeWidth = 3.dp
                            )
                        }
                    }
                    error != null -> {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .weight(1f),
                            contentAlignment = Alignment.Center
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Box(
                                    modifier = Modifier
                                        .size(64.dp)
                                        .clip(CircleShape)
                                        .background(FlowpayMediumGray),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.History,
                                        contentDescription = null,
                                        tint = FlowpayStatusError,
                                        modifier = Modifier.size(32.dp)
                                    )
                                }
                                Spacer(modifier = Modifier.height(16.dp))
                                Text(
                                    text = "Something went wrong",
                                    fontSize = 16.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    color = Color.White
                                )
                                Spacer(modifier = Modifier.height(4.dp))
                                TextButton(onClick = { transactionViewModel.loadHistory() }) {
                                    Text(
                                        "Retry",
                                        color = accent.primary,
                                        fontSize = 14.sp,
                                        fontWeight = FontWeight.Medium
                                    )
                                }
                            }
                        }
                    }
                    filteredTransactions.isEmpty() -> {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .weight(1f),
                            contentAlignment = Alignment.Center
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Box(
                                    modifier = Modifier
                                        .size(64.dp)
                                        .clip(CircleShape)
                                        .background(FlowpayMediumGray),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.History,
                                        contentDescription = null,
                                        tint = FlowpayTextLightGray,
                                        modifier = Modifier.size(32.dp)
                                    )
                                }
                                Spacer(modifier = Modifier.height(16.dp))
                                Text(
                                    text = if (searchQuery.isNotEmpty()) {
                                        "No matching transactions"
                                    } else {
                                        "No transactions yet"
                                    },
                                    fontSize = 16.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    color = Color.White
                                )
                                Spacer(modifier = Modifier.height(4.dp))
                                Text(
                                    text = if (searchQuery.isNotEmpty()) {
                                        "Try a different search"
                                    } else {
                                        "Transactions will appear here"
                                    },
                                    fontSize = 13.sp,
                                    color = FlowpayTextLightGray
                                )
                            }
                        }
                    }
                    else -> {
                        LazyColumn(
                            modifier = Modifier.weight(1f),
                            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp)
                        ) {
                            groupedTransactions.forEach { (dateLabel, transactions) ->
                                // Date section header
                                item(key = "header_$dateLabel") {
                                    Text(
                                        text = dateLabel,
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.SemiBold,
                                        color = FlowpayTextLightGray,
                                        letterSpacing = 0.5.sp,
                                        modifier = Modifier.padding(top = 16.dp, bottom = 8.dp)
                                    )
                                }

                                // Transaction items with dividers
                                itemsIndexed(
                                    items = transactions,
                                    key = { _, tx -> tx.transactionId }
                                ) { index, transaction ->
                                    TransactionHistoryItem(
                                        transaction = transaction,
                                        onClick = { selectedTransaction = transaction }
                                    )
                                    if (index < transactions.lastIndex) {
                                        HorizontalDivider(
                                            modifier = Modifier.padding(start = 52.dp),
                                            thickness = 0.5.dp,
                                            color = FlowpayDarkGray
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }
            SnackbarHost(
                snackbar,
                Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(16.dp)
            )
        }
    }

    // Detail dialog
    selectedTransaction?.let { transaction ->
        TransactionDetailDialog(
            transaction = transaction,
            onDismiss = { selectedTransaction = null },
            onDelete = {
                transactionViewModel.deleteTransaction(transaction)
                selectedTransaction = null
            }
        )
    }
}

// ═══ TRANSACTION ROW — flat, minimal, GPay-style ═══

@Composable
private fun TransactionHistoryItem(
    transaction: Transaction,
    onClick: () -> Unit
) {
    val accent = LocalFlowpayAccentTheme.current
    val displayName = transaction.recipientLabel ?: stringResource(R.string.detail_recipient_unknown)
    val initial = displayName.first().uppercaseChar()

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        TransactionAvatar(initial)

        Spacer(modifier = Modifier.width(12.dp))

        // Name + time
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = displayName,
                fontSize = 15.sp,
                fontWeight = FontWeight.Medium,
                color = Color.White,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = formatTime(transaction.timestamp),
                fontSize = 13.sp,
                color = FlowpayTextLightGray,
                maxLines = 1
            )
        }

        Spacer(modifier = Modifier.width(8.dp))

        // Amount + status pill: the outcome must be readable at a glance, so
        // SUCCESS and UNVERIFIED never look identical in the list.
        Column(horizontalAlignment = Alignment.End) {
            if (transaction.amount.isNotBlank()) {
                Text(
                    text = stringResource(R.string.amount_rupees, CurrencyFormat.inr(transaction.amount)),
                    fontSize = 16.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = Color.White,
                    maxLines = 1
                )
                Spacer(modifier = Modifier.height(4.dp))
            }
            StatusPill(transaction.status)
        }
    }
}

@Composable
private fun TransactionAvatar(initial: Char) {
    Box(
        modifier = Modifier
            .size(40.dp)
            .clip(CircleShape)
            .background(FlowpayDarkGray),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = initial.toString(),
            fontSize = 16.sp,
            fontWeight = FontWeight.SemiBold,
            color = Color.White
        )
    }
}

@Composable
private fun StatusPill(status: String) {
    val statusColor = statusColor(status)
    Text(
        text = stringResource(statusLabelRes(status)),
        fontSize = 11.sp,
        fontWeight = FontWeight.Medium,
        color = statusColor,
        maxLines = 1,
        modifier = Modifier
            .clip(RoundedCornerShape(6.dp))
            .background(statusColor.copy(alpha = 0.15f))
            .padding(horizontal = 8.dp, vertical = 2.dp)
    )
}
