// SPDX-License-Identifier: Apache-2.0
package com.flowpay.app.ui.components

import android.app.Activity
import android.app.Dialog
import android.content.Context
import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.ImageView
import android.widget.TextView
import com.flowpay.app.R
import com.flowpay.app.ui.theme.FlowpayViewTheme

/** Window/view construction only; session ownership and timing remain in the presenter. */
internal object PaymentPromptLayout {
    private const val DIM_AMOUNT = 0.6f
    private const val HORIZONTAL_INSET_DP = 48
    private const val MAX_WIDTH_DP = 380
    private const val DISABLED_ALPHA = 0.5f

    fun create(owner: Context, notice: Boolean, onAnswer: (Boolean, View) -> Unit, onLater: () -> Unit): Dialog {
        val view = LayoutInflater.from(owner).inflate(R.layout.dialog_payment_prompt, null)
        FlowpayViewTheme.observe(view, FlowpayViewTheme::paymentPrompt)
        view.findViewById<TextView>(R.id.paymentPromptTitle).setText(
            if (notice) R.string.payment_callback_title else R.string.payment_outcome_title
        )
        view.findViewById<TextView>(R.id.paymentPromptBody).setText(
            if (notice) R.string.payment_callback_body else R.string.payment_outcome_hint
        )
        view.findViewById<ImageView>(R.id.paymentPromptIcon).apply {
            visibility = if (notice) View.VISIBLE else View.GONE
            setImageResource(R.drawable.ic_payment_call)
        }
        view.findViewById<View>(R.id.paymentPromptAnswers).visibility = if (notice) View.GONE else View.VISIBLE
        view.findViewById<View>(R.id.paymentAnswerYes).setOnClickListener { onAnswer(true, view) }
        view.findViewById<View>(R.id.paymentAnswerNo).setOnClickListener { onAnswer(false, view) }
        view.findViewById<TextView>(R.id.paymentPromptLater).apply {
            setText(if (notice) R.string.payment_callback_later else R.string.payment_answer_later)
            setOnClickListener { onLater() }
        }
        return Dialog(owner, android.R.style.Theme_DeviceDefault_Dialog_NoActionBar).apply {
            setContentView(view)
            setCanceledOnTouchOutside(false)
            setOnCancelListener { onLater() }
            window?.apply {
                setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
                addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND)
                setDimAmount(DIM_AMOUNT)
                if (owner !is Activity) setType(WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY)
                attributes = attributes.apply { windowAnimations = android.R.style.Animation_Dialog }
            }
        }
    }

    fun matches(
        dialog: Dialog?,
        owner: Context,
        displayedOwner: Context?,
        key: String,
        displayedKey: String?
    ): Boolean =
        dialog?.isShowing == true && displayedOwner === owner && displayedKey == key

    fun show(dialog: Dialog, owner: Context): Boolean = try {
        dialog.show()
        size(dialog, owner)
        true
    } catch (_: WindowManager.BadTokenException) {
        false
    } catch (_: SecurityException) {
        false
    }

    fun size(dialog: Dialog, context: Context) {
        val metrics = context.resources.displayMetrics
        val width = minOf(
            metrics.widthPixels - (HORIZONTAL_INSET_DP * metrics.density).toInt(),
            (MAX_WIDTH_DP * metrics.density).toInt()
        )
        dialog.window?.setLayout(width, ViewGroup.LayoutParams.WRAP_CONTENT)
    }

    fun setSaving(dialog: Dialog?, view: View, saving: Boolean) {
        dialog?.setCancelable(!saving)
        for (id in listOf(R.id.paymentAnswerYes, R.id.paymentAnswerNo, R.id.paymentPromptLater)) {
            view.findViewById<View>(id).apply {
                isEnabled = !saving
                alpha = if (saving) DISABLED_ALPHA else 1f
            }
        }
    }
}
