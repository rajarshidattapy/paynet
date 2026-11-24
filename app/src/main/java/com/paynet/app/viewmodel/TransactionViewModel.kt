// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.viewmodel

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.paynet.app.R
import com.paynet.app.data.PaymentDetails
import com.paynet.app.data.Transaction
import com.paynet.app.repository.TransactionRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.emitAll
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class TransactionHistoryState(
    val transactions: List<Transaction> = emptyList(),
    val isLoading: Boolean = true,
    val error: String? = null
)

/** ViewModel for transaction data and UI state. */
class TransactionViewModel(application: Application) : AndroidViewModel(application) {

    /**
     * First repository access materialises the encrypted database (SQLCipher
     * open, Keystore unwrap, possible migration) — expensive disk work that
     * must never run on the main thread. This ViewModel can be the process's
     * first DB toucher (home screen), so resolution is deferred to IO here
     * instead of an eager field initialiser.
     */
    private companion object {
        const val TAG = "TransactionViewModel"
    }

    /** Strings for the error banner come from resources, never from an exception message. */
    private val app: Application get() = getApplication()

    private suspend fun repository(): TransactionRepository =
        withContext(Dispatchers.IO) { TransactionRepository.getInstance(getApplication()) }

    /** Flow variant of [repository]: resolves on IO at collection time. */
    private fun <T> repositoryFlow(block: (TransactionRepository) -> Flow<T>): Flow<T> =
        flow { emitAll(block(TransactionRepository.getInstance(getApplication()))) }
            .flowOn(Dispatchers.IO)

    // UI State
    private val _recentTransactions = MutableStateFlow<List<PaymentDetails>>(emptyList())
    val recentTransactions: StateFlow<List<PaymentDetails>> = _recentTransactions.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    /** The transaction whose detail dialog is open, if any. */
    private val _selectedTransaction = MutableStateFlow<Transaction?>(null)
    val selectedTransaction: StateFlow<Transaction?> = _selectedTransaction.asStateFlow()

    // Room emits updates after writes; keep one observer while this ViewModel lives.
    private var recentTransactionsJob: Job? = null
    private var historyJob: Job? = null
    private val _historyState = MutableStateFlow(TransactionHistoryState())
    val historyState: StateFlow<TransactionHistoryState> = _historyState.asStateFlow()

    fun loadHistory() {
        if (historyJob?.isActive == true) return
        historyJob = viewModelScope.launch {
            _historyState.value = _historyState.value.copy(
                isLoading = _historyState.value.transactions.isEmpty(), error = null
            )
            try {
                repository().getAllTransactions().collect { transactions ->
                    _historyState.value = TransactionHistoryState(transactions, isLoading = false)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.e(TAG, "Failed to load history", e)
                _historyState.value = _historyState.value.copy(
                    isLoading = false, error = app.getString(R.string.error_load_transactions)
                )
            }
        }
    }

    /**
     * Load recent transactions (last 10)
     */
    fun loadRecentTransactions() {
        if (recentTransactionsJob?.isActive == true) return
        recentTransactionsJob = viewModelScope.launch {
            _isLoading.value = _recentTransactions.value.isEmpty()
            _error.value = null

            try {
                repository().getRecentPaymentDetails(10).collect { transactions ->
                    _recentTransactions.value = transactions
                    _isLoading.value = false
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.e(TAG, "Failed to load transactions", e)
                _error.value = app.getString(R.string.error_load_transactions)
                _isLoading.value = false
            }
        }
    }

    /**
     * Open the detail dialog for a recent-payments row. The list carries only
     * the summary [PaymentDetails], so the full row is fetched by id.
     */
    fun selectTransaction(transactionId: String) {
        viewModelScope.launch {
            try {
                _selectedTransaction.value = repository().getTransactionById(transactionId)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.e(TAG, "Failed to open transaction", e)
                _error.value = app.getString(R.string.error_open_transaction)
            }
        }
    }

    /** Close the detail dialog. */
    fun clearSelectedTransaction() {
        _selectedTransaction.value = null
    }

    /**
     * Load all transactions
     */
    private val allTransactions = repositoryFlow { it.getAllTransactions() }

    fun loadAllTransactions(): Flow<List<Transaction>> = allTransactions

    /**
     * Search transactions
     */
    fun searchTransactions(query: String): Flow<List<Transaction>> {
        return repositoryFlow { it.searchTransactions(query) }
    }

    /**
     * Get transactions by status
     */
    fun getTransactionsByStatus(status: String): Flow<List<Transaction>> {
        return repositoryFlow { it.getTransactionsByStatus(status) }
    }

    /**
     * Get transactions by bank
     */
    fun getTransactionsByBank(bankName: String): Flow<List<Transaction>> {
        return repositoryFlow { it.getTransactionsByBank(bankName) }
    }

    /**
     * Delete a transaction
     */
    fun deleteTransaction(transaction: Transaction) {
        viewModelScope.launch {
            try {
                repository().deleteTransaction(transaction)
                // Existing Room observers receive this change automatically.
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.e(TAG, "Failed to delete transaction", e)
                _error.value = app.getString(R.string.error_delete_transaction)
            }
        }
    }

    /**
     * Delete transaction by ID
     */
    fun deleteTransactionById(transactionId: String) {
        viewModelScope.launch {
            try {
                repository().deleteTransactionById(transactionId)
                // Existing Room observers receive this change automatically.
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.e(TAG, "Failed to delete transaction", e)
                _error.value = app.getString(R.string.error_delete_transaction)
            }
        }
    }

    /**
     * Clear all transactions
     */
    fun clearAllTransactions() {
        viewModelScope.launch {
            try {
                repository().deleteAllTransactions()
                _recentTransactions.value = emptyList()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.e(TAG, "Failed to clear transactions", e)
                _error.value = app.getString(R.string.error_clear_transactions)
            }
        }
    }

    /**
     * Clear error state
     */
    fun clearError() {
        _error.value = null
    }

    /**
     * Refresh data
     */
    fun refresh() {
        _error.value = null
        loadRecentTransactions()
    }
}
