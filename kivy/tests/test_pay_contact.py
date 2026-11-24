# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay

"""Pay-contact flow (feature 10): state validation, contact filtering,
dialog behavior and the transfer-initiation gates. Pure widget
construction — no window is opened."""

import os

os.environ.setdefault("KIVY_NO_ARGS", "1")

from paynet.ui.pay_contact import (
    Contact,
    ContactPickerDialog,
    PayContactDialog,
    PayContactState,
    UnavailableContactProvider,
    filter_contacts,
)
from paynet.payment.initiate import (
    STR_ENTER_PHONE_AND_AMOUNT,
    STR_INVALID_AMOUNT,
    STR_INVALID_PHONE,
    TransferInitiator,
)
from paynet.utils import phone as phone_input


def _walk(widget):
    yield widget
    for child in widget.children:
        yield from _walk(child)


def _labels(widget):
    from kivy.uix.label import Label

    return [w.text for w in _walk(widget) if isinstance(w, Label)]


# -- state ---------------------------------------------------------------------


def test_can_transfer_requires_pattern_and_range():
    state = PayContactState()
    assert not state.can_transfer
    state.phone_number = "9123456780"
    assert not state.can_transfer  # no amount yet
    state.amount = "0"
    assert not state.can_transfer
    state.amount = "5000"
    assert not state.can_transfer  # above the 4,999 cap
    state.amount = "4999"
    assert state.can_transfer
    state.phone_number = "0123456789"  # leading zero
    assert not state.can_transfer
    state.phone_number = "912345678"  # 9 digits
    assert not state.can_transfer


def test_is_over_cap():
    state = PayContactState()
    state.amount = "4999"
    assert not state.is_over_cap
    state.amount = "5000"
    assert state.is_over_cap
    state.amount = "not-a-number"
    assert not state.is_over_cap


def test_update_phone_normalizes_and_rejects():
    state = PayContactState()
    assert state.update_phone("91234 56780") == "9123456780"
    assert state.update_phone("+919123456780") == "9123456780"
    assert state.update_phone("09123456780") == "9123456780"
    # A rejected edit returns the current text unchanged.
    assert state.update_phone("91234abcde780") == "9123456780"
    assert state.phone_number == "9123456780"


def test_update_phone_edits_clear_selected_contact():
    state = PayContactState()
    state.select_contact("9123456780", "Kirana Store")
    state.update_phone("9123456781")
    assert state.selected_contact_name is None


def test_select_contact():
    state = PayContactState()
    state.show_contact_picker = True
    state.select_contact("9123456780", "Kirana Store")
    assert state.phone_number == "9123456780"
    assert state.selected_contact_name == "Kirana Store"
    assert not state.show_contact_picker


# -- contact filtering ------------------------------------------------------------


def _contacts():
    return [
        Contact("1", "Kirana Store", "9123456780"),
        Contact("2", "Rahul Sharma", "9876501234"),
    ]


def test_filter_contacts_by_name():
    assert [c.name for c in filter_contacts(_contacts(), "kirana")] == [
        "Kirana Store"]


def test_filter_contacts_by_number_and_country_code():
    assert [c.name for c in filter_contacts(_contacts(), "912345")] == [
        "Kirana Store"]
    assert [c.name for c in filter_contacts(_contacts(), "919123456780")] == [
        "Kirana Store"]


def test_filter_contacts_blank_returns_all():
    assert len(filter_contacts(_contacts(), "  ")) == 2


def test_filter_contacts_name_term_never_matches_number():
    # A term that is not number-ish must not match digits.
    assert filter_contacts(_contacts(), "store 9123456780") == []


# -- dialog ---------------------------------------------------------------------


class _FakeProvider:
    def __init__(self, granted=True, contacts=()):
        self._granted = granted
        self._contacts = contacts

    def has_contact_permission(self):
        return self._granted

    def request_contact_permission(self, on_result):
        on_result(self._granted)

    def load_contacts(self):
        return list(self._contacts)


def _dialog(on_confirm=lambda *a: None, provider=None):
    return PayContactDialog(on_dismiss=lambda: None, on_confirm=on_confirm,
                            contact_provider=provider)


def test_transfer_disabled_until_valid():
    dialog = _dialog()
    dialog._confirm()
    assert dialog.state.can_transfer is False
    dialog.phone_field.input.text = "9123456780"
    dialog.amount_field.input.text = "240"
    assert dialog.state.can_transfer is True


def test_confirm_passes_phone_amount_name():
    seen = []
    dialog = _dialog(on_confirm=lambda p, a, n: seen.append((p, a, n)))
    dialog._contact_selected(Contact("1", "Kirana Store", "9123456780"))
    dialog.amount_field.input.text = "240"
    dialog._confirm()
    assert seen == [("9123456780", "240", "Kirana Store")]


def test_amount_field_digits_only_and_capped():
    dialog = _dialog()
    dialog.amount_field.input.text = "12a45"
    assert dialog.amount_field.input.text == "1245"
    dialog.amount_field.input.text = "1234567"
    assert dialog.amount_field.input.text == "123456"


def test_over_cap_marks_error_and_blocks_transfer():
    dialog = _dialog()
    dialog.phone_field.input.text = "9123456780"
    dialog.amount_field.input.text = "6000"
    assert dialog.amount_field._error
    assert dialog._cap_label.opacity == 1
    assert "Maximum" in dialog._cap_label.text
    assert not dialog.state.can_transfer


def test_contact_picker_opens_with_permission():
    provider = _FakeProvider(granted=True,
                             contacts=[Contact("1", "Kirana Store",
                                               "9123456780")])
    dialog = _dialog(provider=provider)
    dialog.choose_contact()
    assert isinstance(dialog._picker, ContactPickerDialog)
    assert "Kirana Store" in _labels(dialog._picker)


def test_permission_dialog_when_ungranted():
    provider = _FakeProvider(granted=False,
                             contacts=[Contact("1", "Kirana Store",
                                               "9123456780")])
    dialog = _dialog(provider=provider)
    dialog.choose_contact()
    assert dialog._picker is None
    assert dialog._permission_dialog is not None
    texts = _labels(dialog._permission_dialog)
    assert "Choose from contacts" in texts
    assert "Allow contacts access to choose someone by name." in texts
    dialog._permission_dialog = None


def test_unavailable_provider_picker_load_failure_state():
    dialog = _dialog(provider=UnavailableContactProvider())
    dialog._open_picker()
    texts = _labels(dialog._picker)
    assert "Couldn’t load contacts. Please try again." in texts
    assert "Try again" in texts


def test_picker_selection_fills_fields():
    provider = _FakeProvider(granted=True,
                             contacts=[Contact("1", "Kirana Store",
                                               "9123456780")])
    dialog = _dialog(provider=provider)
    dialog.choose_contact()
    dialog._contact_selected(Contact("1", "Kirana Store", "9123456780"))
    assert dialog._picker is None
    assert dialog.phone_field.input.text == "9123456780"
    assert dialog.state.selected_contact_name == "Kirana Store"
    assert "Paying Kirana Store" in _labels(dialog)


# -- transfer initiator ------------------------------------------------------------


class _FakeSessionManager:
    def __init__(self):
        self.begun = []

    def begin(self, phone_number, amount, recipient_name=None):
        self.begun.append((phone_number, amount, recipient_name))
        return "txn-1"


class _FakeTestResults:
    def __init__(self, enabled=True):
        self._enabled = enabled

    def get_test_results(self):
        class R:
            pass
        r = R()
        r.upi123Enabled = self._enabled
        return r


def _initiator(enabled=True):
    toasts = []
    setup_calls = []
    calls = []
    session = _FakeSessionManager()
    initiator = TransferInitiator(
        _FakeTestResults(enabled), session,
        show_toast=toasts.append,
        on_setup_required=lambda: setup_calls.append(1),
        place_call=lambda p, a: calls.append((p, a)) or True)
    return initiator, session, toasts, setup_calls, calls


def test_initiator_validates_inputs():
    initiator, session, toasts, _, _ = _initiator()
    assert initiator.initiate_transfer("", "") is None
    assert toasts[-1] == STR_ENTER_PHONE_AND_AMOUNT
    assert initiator.initiate_transfer("123", "240") is None
    assert toasts[-1] == STR_INVALID_PHONE
    assert initiator.initiate_transfer("9123456780", "0") is None
    assert toasts[-1] == STR_INVALID_AMOUNT
    assert initiator.initiate_transfer("9123456780", "6000") is None
    assert "Maximum" in toasts[-1]
    assert session.begun == []


def test_initiator_requires_upi123_enabled():
    initiator, session, toasts, setup_calls, calls = _initiator(enabled=False)
    assert initiator.initiate_transfer("9123456780", "240") is None
    assert setup_calls == [1]
    assert session.begun == []
    assert calls == []


def test_initiator_begins_session_and_places_call():
    initiator, session, _, _, calls = _initiator()
    txn = initiator.initiate_transfer("9123456780", "240",
                                      recipient_name="Kirana Store")
    assert txn == "txn-1"
    assert session.begun == [("9123456780", "240", "Kirana Store")]
    assert calls == [("9123456780", "240")]


def test_initiator_without_telephony_never_dials():
    toasts = []
    session = _FakeSessionManager()
    initiator = TransferInitiator(
        _FakeTestResults(True), session, show_toast=toasts.append)
    # place_call stays None: the desktop build must not dial.
    assert initiator._place_call is None
    assert initiator.initiate_transfer("9123456780", "240") == "txn-1"
    assert session.begun == [("9123456780", "240", None)]
