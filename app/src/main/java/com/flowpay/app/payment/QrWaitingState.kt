// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.payment

import com.flowpay.app.states.PaymentState

/** A deadline ends the waiting UI without asserting a bank outcome or closing the SMS grace window. */
fun shouldCloseQrWaitingScreen(transactionId: String?, state: PaymentState): Boolean =
    transactionId != null && state.getTransactionIdValue() == transactionId &&
        (state.isTerminal() || state is PaymentState.Timeout)
