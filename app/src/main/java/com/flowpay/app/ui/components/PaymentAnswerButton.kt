// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.ui.components

import android.content.Context
import android.util.AttributeSet
import android.widget.LinearLayout

/** Keeps the icon and label centered as one group while retaining a button role for TalkBack. */
class PaymentAnswerButton @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : LinearLayout(context, attrs, defStyleAttr) {
    override fun getAccessibilityClassName(): CharSequence = android.widget.Button::class.java.name
}
