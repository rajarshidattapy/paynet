# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported coverage for PaymentResultActivity's presentation logic and the
# TransactionDialogManager / prompt component behavior. The Kotlin sources
# ship no tests for these beyond PaymentPromptTimingTest (already ported in
# feature 11); these lock the ported rules.

import pytest

from paynet import theme
from paynet import status as TransactionStatus
from paynet.ui import prompts, result


class TestBankReference:
    # bankReferenceOf: ids are stored as `<bank reference>_<timestamp>`.
    def test_strips_timestamp_suffix(self):
        assert result.bank_reference_of("HDFC123456_1720000000000") == "HDFC123456"

    def test_generated_id_without_separator_shows_as_is(self):
        assert result.bank_reference_of("txn-42") == "txn-42"

    def test_reference_containing_underscore_keeps_everything_before_last(self):
        assert result.bank_reference_of("UTIB_9988_1720000000000") == "UTIB_9988"

    def test_trailing_underscore_only_keeps_head(self):
        assert result.bank_reference_of("ABC_") == "ABC"

    def test_leading_separator_has_no_head(self):
        assert result.bank_reference_of("_1720000000000") == "_1720000000000"


class TestCounterpartyLabel:
    # "Paid to"/"Received from" are past tense: only SUCCESS earns them.
    def test_success_credit_is_received_from(self):
        assert result.counterparty_label_for("SUCCESS", "CREDIT") == "Received from"

    def test_success_debit_is_paid_to(self):
        assert result.counterparty_label_for("SUCCESS", "DEBIT") == "Paid to"

    def test_failed_credit_stays_from(self):
        assert result.counterparty_label_for("FAILED", "CREDIT") == "From"

    def test_unverified_debit_stays_to(self):
        assert result.counterparty_label_for("UNVERIFIED", "DEBIT") == "To"


class TestRecipientRow:
    def test_named_recipient_wins(self):
        assert result.recipient_row("Asha", "+911", "UPI_123", "+9199",
                                    "SUCCESS", "DEBIT") == ("Paid to", "Asha")

    def test_phone_fallback(self):
        assert result.recipient_row(None, "+911234", "USSD", None,
                                    "FAILED", "DEBIT") == ("To", "+911234")

    def test_upi123_detector_phone_fallback(self):
        assert result.recipient_row(None, None, "UPI_123", "+9198123",
                                    "UNVERIFIED", "DEBIT") == ("To", "+9198123")

    def test_no_recipient_info_hides_row(self):
        assert result.recipient_row(None, None, "USSD", None,
                                    "SUCCESS", "DEBIT") is None


class TestResultPresentation:
    # Only an explicit SUCCESS earns the success styling.
    def test_success_uses_accent_and_check(self):
        presentation = result.result_presentation("SUCCESS", theme.VIOLET_ACCENT_THEME.primary)
        assert presentation["title"] == "Payment Successful"
        assert presentation["explainer"] is None
        assert presentation["glyph"] == "check"
        assert presentation["accent"] == theme.VIOLET_ACCENT_THEME.primary

    def test_failed_uses_error_color(self):
        presentation = result.result_presentation("FAILED", theme.VIOLET_ACCENT_THEME.primary)
        assert presentation["title"] == "Payment Failed"
        assert "auto-reversed" in presentation["explainer"]
        assert presentation["accent"] == theme.STATUS_ERROR

    def test_needs_review_uses_warning(self):
        presentation = result.result_presentation("NEEDS_REVIEW", theme.VIOLET_ACCENT_THEME.primary)
        assert presentation["title"] == "Check This Payment"
        assert presentation["accent"] == theme.STATUS_WARNING

    def test_unknown_status_renders_neutral_never_success(self):
        for unexpected in ("UNVERIFIED", "CANCELLED", "", "PENDING"):
            presentation = result.result_presentation(unexpected, theme.VIOLET_ACCENT_THEME.primary)
            assert presentation["title"] == "No Confirmation Received"
            assert presentation["accent"] == theme.STATUS_NEUTRAL


class TestResultFormatting:
    def test_amount_prefixes_rupee_sign(self):
        assert result.format_result_amount("1500.0") == "₹1,500.00"

    def test_datetime_matches_dd_mmm_yyyy_hh_mm_a(self):
        # 2026-11-24T10:07:00 UTC = 15:37 IST.
        text = result.format_result_datetime(1764014820000)
        parts = text.split(" ")
        assert len(parts) == 5  # "24 Nov 2026, 03:37 PM"
        assert parts[1] == "Nov" and parts[3].count(":") == 1


class TestSetupDialogs:
    def test_ussd_dialog_starts_without_shortcuts(self):
        dialog = prompts.ussd_progress_dialog()
        assert dialog.shortcuts_revealed is False
        built = dialog.build()
        # Only the progress content, no actions yet.
        assert built._actions.children == []

    def test_shortcuts_reveal_adds_ready_and_does_not_work(self):
        hits = []
        dialog = prompts.ussd_progress_dialog(
            on_configured=lambda: hits.append("configured"),
            on_does_not_work=lambda: hits.append("nope"))
        dialog._reveal_shortcuts()
        built = dialog.build()
        assert [a.text for a in reversed(built._actions.children)] == \
            ["It's already set up", "It isn't working"]
        built._actions.children[-1]._on_release_cb()  # "It's already set up"
        built._actions.children[0]._on_release_cb()   # "It isn't working"
        assert hits == ["configured", "nope"]

    def test_upi123_shortcut_has_no_does_not_work(self):
        dialog = prompts.upi123_progress_dialog()
        dialog._reveal_shortcuts()
        built = dialog.build()
        assert [a.text for a in built._actions.children] == ["It's already set up"]

    def test_confirmation_options_swap_copy_and_actions(self):
        hits = []
        dialog = prompts.upi123_progress_dialog(
            on_configured=lambda: hits.append("configured"),
            on_not_configured=lambda: hits.append("not"))
        dialog.show_confirmation_options()
        built = dialog.build()
        assert built._actions.children[1].text == "Yes, it's set up"
        assert built._actions.children[0].text == "Not yet"
        built._actions.children[0]._on_release_cb()
        assert hits == ["not"]

    def test_upi123_progress_step_is_waiting_for_setup(self):
        dialog = prompts.upi123_progress_dialog()
        assert dialog._titles[4] == "Waiting for setup"


class TestTransactionDialogManager:
    def make(self, factory=None):
        self.dismissals = 0
        self.toasts = []
        self.dialogs = []
        manager = prompts.TransactionDialogManager(
            dialog_factory=factory or self._factory,
            toast=self.toasts.append,
            on_any_dismiss=lambda: setattr(self, "dismissals", self.dismissals + 1))
        return manager

    def _factory(self, title, message, button, on_dismiss=None):
        record = (title, message, button, on_dismiss)
        self.dialogs.append(record)
        return record

    def test_cancelled_dialog_content(self):
        manager = self.make()
        manager.show_transaction_cancelled()
        title, message, button, _ = self.dialogs[0]
        assert title == "Transaction Cancelled"
        assert "call ended" in message
        assert button == "OK"

    def test_cancelled_by_user_has_distinct_message(self):
        manager = self.make()
        manager.show_transaction_cancelled_by_user()
        assert "cancelled" in self.dialogs[0][1].lower()
        assert "call ended" not in self.dialogs[0][1]

    def test_dismiss_acknowledges_session(self):
        manager = self.make()
        manager.show_transaction_failed()
        self.dialogs[0][3]()  # user dismissed
        assert self.dismissals == 1

    def test_awaiting_confirmation_never_acknowledges(self):
        manager = self.make()
        manager.show_awaiting_confirmation()
        title, message, button, on_dismiss = self.dialogs[0]
        assert title == "Request Sent" and button == "Got it"
        assert on_dismiss is None

    def test_dialog_failure_falls_back_to_toast_and_acknowledges(self):
        def broken(*_args, **_kwargs):
            raise RuntimeError("window died")

        manager = self.make(factory=broken)
        manager.show_transaction_failed()
        assert self.toasts == ["Your bank reported the payment as failed."]
        assert self.dismissals == 1

    def test_awaiting_failure_toasts_without_acknowledging(self):
        def broken(*_args, **_kwargs):
            raise RuntimeError("window died")

        manager = self.make(factory=broken)
        manager.show_awaiting_confirmation()
        assert self.toasts == ["Return to PayNet to record the outcome."]
        assert self.dismissals == 0


class TestPaymentPrompt:
    def test_outcome_prompt_has_yes_no_and_later(self):
        prompt = prompts.PaymentPrompt(notice=False)
        dialog = prompt.build()
        assert [a.text for a in reversed(dialog._actions.children)] == \
            ["Yes", "No", "Not sure"]

    def test_notice_prompt_has_only_later(self):
        prompt = prompts.PaymentPrompt(notice=True)
        dialog = prompt.build()
        assert [a.text for a in dialog._actions.children] == ["Not now"]

    def test_answer_routes_yes_and_no(self):
        answers = []
        prompt = prompts.PaymentPrompt(on_answer=answers.append)
        dialog = prompt.build()
        dialog._actions.children[2]._on_release_cb()  # Yes
        dialog._actions.children[1]._on_release_cb()  # No
        assert answers == [True, False]

    def test_cancel_routes_to_later(self):
        laters = []
        prompt = prompts.PaymentPrompt(on_later=lambda: laters.append(1))
        prompt.build()
        prompt._dialog._on_dismiss()
        assert laters == [1]

    def test_saving_disables_answers_at_half_alpha(self):
        prompt = prompts.PaymentPrompt()
        prompt.build()
        prompt.set_saving(True)
        assert all(a.disabled for a in prompt.answers)
        assert all(a.opacity == pytest.approx(0.5) for a in prompt.answers)
        prompt.set_saving(False)
        assert all(not a.disabled for a in prompt.answers)

    def test_matches_requires_showing_and_same_key(self):
        prompt = prompts.PaymentPrompt()
        assert prompt.matches("k", "k", showing=True)
        assert not prompt.matches("k", "other", showing=True)
        assert not prompt.matches("k", "k", showing=False)

    def test_width_capped_at_380dp_minus_inset(self):
        assert prompts.PaymentPrompt.width_for(1400, density=3.0) == 380 * 3.0
        assert prompts.PaymentPrompt.width_for(400, density=1.0) == 400 - 48


class TestSmsPermissionNotice:
    def test_hidden_when_already_granted(self):
        notice = prompts.SmsPermissionNotice(permission_granted=lambda: True)
        assert notice.build() is None

    def test_allow_requests_permissions_and_dismisses(self):
        calls = []
        notice = prompts.SmsPermissionNotice(
            permission_granted=lambda: False,
            request_permissions=lambda: calls.append("requested"))
        notice.build()
        notice._allow()
        assert calls == ["requested"]
        assert notice.dismissed and notice.requested
        assert notice.build() is None

    def test_later_dismisses_without_requesting(self):
        calls = []
        notice = prompts.SmsPermissionNotice(request_permissions=lambda: calls.append(1))
        notice.build()
        notice._dismiss()
        assert calls == [] and notice.dismissed
