// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Flowpay

package com.paynet.app.data

object TransactionStatus {
    const val PENDING = "PENDING"
    const val SUCCESS = "SUCCESS"
    const val FAILED = "FAILED"
    const val CANCELLED = "CANCELLED"
    const val UNVERIFIED = "UNVERIFIED"
    const val NEEDS_REVIEW = "NEEDS_REVIEW"
}

/** Where a transaction record originated. */
object TransactionSource {
    const val SMS = "SMS"
    const val MANUAL = "MANUAL"
    const val QR = "QR"
}
