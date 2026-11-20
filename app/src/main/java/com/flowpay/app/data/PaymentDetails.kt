// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.flowpay.app.data

/**
 * Data class representing payment transaction details
 * Used for storing and managing payment information
 */
data class PaymentDetails(
    val id: String,
    val recipientName: String? = null,
    val phoneNumber: String,
    val amount: Double,
    val timestamp: Long,
    val status: PaymentStatus,
    val userConfirmed: Boolean? = null,
    val amountRecorded: Boolean = true
) {
    val recipientLabel: String?
        get() = recipientName?.trim()?.takeIf { it.isNotEmpty() }
            ?: phoneNumber.trim().takeIf { it.isNotEmpty() }
}
