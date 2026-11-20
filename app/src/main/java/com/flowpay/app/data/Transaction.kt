// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.flowpay.app.data

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "transactions",
    indices = [Index("timestamp"), Index("status")]
)
data class Transaction(
    @PrimaryKey
    val transactionId: String,
    val amount: String,
    val status: String,
    val bankName: String,

    // Privacy-safe summary from parsed fields; never stores the raw SMS body.
    val smsExcerpt: String,
    val timestamp: Long = System.currentTimeMillis(),
    val upiId: String? = null,
    val transactionType: String = "DEBIT",
    val recipientName: String? = null,
    val phoneNumber: String? = null,
    val bankRef: String? = null,
    val deadlineAt: Long? = null,
    val source: String? = null,
    val verifiedAt: Long? = null
) {
    /**
     * Convert to PaymentDetails for UI compatibility
     */
    val displayRecipient: String?
        get() = recipientName?.trim()?.takeIf { it.isNotEmpty() }?.let { name ->
            if ('@' in name || name.none { it.isLetter() }) {
                name
            } else {
                Regex("\\p{L}[\\p{L}\\p{M}]*").replace(name) { word ->
                    word.value.lowercase(java.util.Locale.ROOT).replaceFirstChar { it.titlecase(java.util.Locale.ROOT) }
                }
            }
        }

    /** The same identity fallback is used by every transaction surface. */
    val recipientLabel: String?
        get() = displayRecipient
            ?: phoneNumber?.trim()?.takeIf { it.isNotEmpty() }
            ?: upiId?.trim()?.takeIf { it.isNotEmpty() }

    fun toPaymentDetails(): PaymentDetails {
        return PaymentDetails(
            id = transactionId,
            recipientName = recipientLabel,
            phoneNumber = phoneNumber ?: "",
            amount = amount.toDoubleOrNull() ?: 0.0,
            timestamp = timestamp,
            amountRecorded = amount.isNotBlank(),
            userConfirmed = when (status) {
                "USER_CONFIRMED" -> true
                "USER_NOT_CONFIRMED" -> false
                else -> null
            },
            status = when (status.uppercase()) {
                "SUCCESS", "SUCCESSFUL", "COMPLETED" -> PaymentStatus.COMPLETED
                "UNVERIFIED", "USER_CONFIRMED", "USER_NOT_CONFIRMED" -> PaymentStatus.UNVERIFIED
                "NEEDS_REVIEW" -> PaymentStatus.NEEDS_REVIEW
                "PENDING" -> PaymentStatus.PENDING
                "CANCELLED" -> PaymentStatus.CANCELLED
                "FAILED", "DECLINED" -> PaymentStatus.FAILED
                else -> PaymentStatus.PENDING
            }
        )
    }
    companion object {
        fun fromSimpleTransaction(simpleTransaction: com.flowpay.app.payment.sms.SimpleTransaction): Transaction {
            return Transaction(
                transactionId = simpleTransaction.transactionId,
                amount = simpleTransaction.amount,
                status = simpleTransaction.status,
                bankName = simpleTransaction.bankName,
                smsExcerpt = simpleTransaction.smsExcerpt,
                timestamp = simpleTransaction.timestamp,
                upiId = simpleTransaction.upiId,
                transactionType = simpleTransaction.transactionType,
                recipientName = simpleTransaction.recipientName,
                phoneNumber = simpleTransaction.phoneNumber,
                bankRef = simpleTransaction.transactionId,
                source = TransactionSource.SMS
            )
        }
    }
}
