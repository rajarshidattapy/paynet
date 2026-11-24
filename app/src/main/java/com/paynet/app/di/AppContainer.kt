// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay
package com.paynet.app.di

import android.content.Context
import com.paynet.app.data.SettingsRepository
import com.paynet.app.data.Transaction
import com.paynet.app.payment.PaymentSessionManager
import com.paynet.app.payment.PaymentTransactionStore
import com.paynet.app.repository.TransactionRepository
import com.paynet.app.telephony.CallStateCoordinator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.withContext

class AppContainer(context: Context) {
    private val appContext = context.applicationContext
    val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    val settingsRepository by lazy { SettingsRepository(appContext) }
    val callStateCoordinator by lazy { CallStateCoordinator(appContext) }
    val paymentWindowObserver by lazy {
        com.paynet.app.payment.PaymentWindowObserver(appContext, paymentSessionManager.paymentState, appScope)
    }
    val paymentSessionManager by lazy {
        PaymentSessionManager(LazyTransactionStore(appContext), callStateCoordinator, appScope)
    }
}

private class LazyTransactionStore(private val appContext: Context) : PaymentTransactionStore {
    private suspend fun repo() = withContext(Dispatchers.IO) {
        TransactionRepository.getInstance(appContext)
    }
    override suspend fun insertPending(transaction: Transaction) = repo().insertPending(transaction)
    override suspend fun transitionStatus(transactionId: String, expectedStatus: String, newStatus: String) =
        repo().transitionStatus(transactionId, expectedStatus, newStatus)
    override suspend fun deleteStalePending(now: Long) = repo().deleteStalePending(now)
    override suspend fun confirmTransaction(
        transactionId: String,
        status: String,
        parsed: com.paynet.app.payment.sms.SimpleTransaction,
        verifiedAt: Long
    ) =
        repo().confirmTransaction(transactionId, status, parsed, verifiedAt)
    override suspend fun deletePending(transactionId: String) = repo().deletePending(transactionId)
}
