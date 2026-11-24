# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/PayContactContent.kt,
# app/src/main/java/com/paynet/app/ui/dialogs/ContactPickerDialog.kt and
# the PermissionExplanationDialog in MainActivity.kt.

"""Pay-a-contact dialog: validated phone + amount entry, an optional
contact picker, and a confirm callback that hands the inputs to the
initiate-transfer path. The dialog itself never touches telephony."""

from typing import Callable, List, Optional, Protocol

from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from paynet import constants, theme
from paynet.payment.call_string import Reason
from paynet.payment.messages import message_for
from paynet.ui.history import _Divider
from paynet.ui.home import Glyph
from paynet.ui.home_legacy import _IconButton, _TextLink, _left_label, _white
from paynet.utils import phone as phone_input

# -- strings.xml ---------------------------------------------------------------
STR_TITLE = "Pay a contact"
STR_TRANSFER = "Transfer"
STR_CANCEL = "Cancel"
STR_RECIPIENT = "Paying %s"
STR_MOBILE_LABEL = "Mobile number"
STR_MOBILE_HINT = "10 digits"
STR_AMOUNT_LABEL = "Amount (₹)"
STR_AMOUNT_HINT = "Enter amount"
STR_CHOOSE_CONTACT = "Choose a contact"
STR_CONTACTS_PERMISSION_TITLE = "Choose from contacts"
STR_CONTACTS_PERMISSION_BODY = "Allow contacts access to choose someone by name."
STR_PERMISSION_CONTINUE = "Continue"
STR_NOT_NOW = "Not now"
STR_NO_CONTACTS_ACCESS = "Unable to open contacts from this screen."
STR_CONTACTS_TITLE = "Choose a contact"
STR_CONTACTS_CLOSE = "Close contacts"
STR_CONTACTS_SEARCH_HINT = "Search contacts…"
STR_CONTACTS_EMPTY = "No contacts found"
STR_CONTACTS_NO_MATCHES = "No matching contacts"
STR_CONTACTS_FAILED = "Couldn’t load contacts. Please try again."
STR_CONTACTS_RETRY = "Try again"

MAX_AMOUNT_INPUT_DIGITS = 6

_INDIAN_NUMBER_WITH_COUNTRY_CODE_LENGTH = 12
_INDIAN_COUNTRY_CODE = "91"


class Contact:
    """ContactPickerDialog.Contact."""

    def __init__(self, id: str, name: str, phone_number: str):
        self.id = id
        self.name = name
        self.phone_number = phone_number


def filter_contacts(contacts: List[Contact], query: str) -> List[Contact]:
    term = query.strip()
    if not term:
        return contacts
    digits = "".join(c for c in term if c.isdigit())
    if (len(digits) == _INDIAN_NUMBER_WITH_COUNTRY_CODE_LENGTH
            and digits.startswith(_INDIAN_COUNTRY_CODE)):
        number = digits[len(_INDIAN_COUNTRY_CODE):]
    else:
        number = digits
    numberish = all(c.isdigit() or c in "+- ()" for c in term)
    return [
        contact for contact in contacts
        if term.lower() in contact.name.lower()
        or (number and numberish and number in contact.phone_number)
    ]


class ContactProvider(Protocol):
    """The device boundary the Kotlin code reaches through PermissionManager
    and ContactsContract. Desktop provides no contacts; an Android build
    supplies the real implementation (pyjnius/plyer)."""

    def has_contact_permission(self) -> bool:
        ...

    def request_contact_permission(self, on_result: Callable[[bool], None]) -> None:
        ...

    def load_contacts(self) -> List[Contact]:
        ...


class UnavailableContactProvider:
    """No contacts API off-device: permission flow proceeds, the load fails
    and the picker shows its retry state, exactly like a denied phone."""

    def has_contact_permission(self) -> bool:
        return False

    def request_contact_permission(self, on_result: Callable[[bool], None]) -> None:
        on_result(False)

    def load_contacts(self) -> List[Contact]:
        raise RuntimeError("contacts unavailable on this platform")


class PayContactState:
    """PayContactState: normalization, cap check and transfer readiness.
    Kivy's TextInput owns the selection, so only the text semantics port."""

    def __init__(self) -> None:
        self.phone_number = ""
        self.amount = ""
        self.selected_contact_name: Optional[str] = None
        self.show_contact_picker = False
        self.show_contact_permission_dialog = False

    @property
    def is_over_cap(self) -> bool:
        try:
            amount = int(self.amount)
        except ValueError:
            amount = 0
        return amount > constants.UPI123PAY_MAX_AMOUNT

    @property
    def can_transfer(self) -> bool:
        import re

        if re.fullmatch(constants.PHONE_NUMBER_PATTERN, self.phone_number) is None:
            return False
        try:
            amount = int(self.amount)
        except ValueError:
            return False
        return 1 <= amount <= constants.UPI123PAY_MAX_AMOUNT

    def update_phone(self, proposed: str) -> str:
        """Returns the accepted text (a rejected edit returns the current
        text, so the caller can reset the field)."""
        accepted = phone_input.normalize(phone_input.TextValue(
            proposed, phone_input.TextRange(len(proposed), len(proposed))))
        if accepted is None:
            return self.phone_number
        if accepted.text != self.phone_number:
            self.selected_contact_name = None
        self.phone_number = accepted.text
        return accepted.text

    def select_contact(self, number: str, name: str) -> None:
        self.phone_number = number
        self.selected_contact_name = name
        self.show_contact_picker = False


# -- shared dialog shell --------------------------------------------------------


class _DialogScrim(ButtonBehavior, FloatLayout):
    """Dimmed full-screen tap-to-dismiss layer behind a dialog."""

    def __init__(self, on_dismiss, **kwargs):
        super().__init__(**kwargs)
        self._on_dismiss = on_dismiss
        with self.canvas.before:
            Color(rgba=(0, 0, 0, 0.6))
            self._scrim = RoundedRectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda *_: setattr(self._scrim, "pos", self.pos),
                  size=lambda *_: setattr(self._scrim, "size", self.size))

    def on_release(self):
        self._on_dismiss()


class _DialogCard(FloatLayout):
    """AlertDialog port: DarkGray rounded-20 card with title, content and
    trailing action links."""

    def __init__(self, title: str, actions, content, palette,
                 width=None, height=None, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (width or dp(340), height or dp(320))
        with self.canvas.before:
            Color(rgba=theme.DARK_GRAY)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size,
                                        radius=[dp(20)])
        self.bind(pos=lambda *_: setattr(self._bg, "pos", self.pos),
                  size=lambda *_: setattr(self._bg, "size", self.size))

        col = BoxLayout(orientation="vertical", spacing=dp(12),
                        padding=[dp(24), dp(20)],
                        pos_hint={"x": 0, "y": 0})
        self.add_widget(col)
        title_label = _left_label(title, "18sp", (1, 1, 1, 1), bold=True)
        title_label.size_hint_y = None
        title_label.height = dp(28)
        col.add_widget(title_label)
        col.add_widget(content)
        actions_row = BoxLayout(orientation="horizontal", spacing=dp(16),
                                size_hint_y=None, height=dp(44))
        actions_row.add_widget(Widget())  # push actions to the trailing edge
        for text, color, callback in actions:
            width_hint = max(len(text) * 8 + 16, 64)
            actions_row.add_widget(_TextLink(
                text, callback, font_size="14sp", bold=True, color=color,
                halign="center", size_hint_x=None, width=dp(width_hint)))
        col.add_widget(actions_row)


class _Field(FloatLayout):
    """OutlinedTextField port: label above, rounded outline, single-line
    input. The error state recolors the outline."""

    HEIGHT = 64

    def __init__(self, label, hint, palette, numeric=False, **kwargs):
        super().__init__(size_hint_y=None, height=dp(self.HEIGHT), **kwargs)
        self._palette = palette
        self._error = False
        caption = _left_label(label, "12sp", theme.TEXT_LIGHT_GRAY)
        caption.size_hint = (None, None)
        caption.height = dp(18)
        caption.pos_hint = {"x": 0, "top": 1}
        caption.bind(width=lambda w, _: setattr(w, "text_size",
                                                (w.width, None)))
        self.add_widget(caption)
        self.input = TextInput(
            text="", hint_text=hint,
            hint_text_color=theme.ONBOARDING_SECONDARY,
            foreground_color=(1, 1, 1, 1),
            cursor_color=palette.accent,
            font_size="15sp", multiline=False,
            background_color=(0, 0, 0, 0),
            background_normal="", background_active="",
            padding=[dp(12), dp(10)],
            input_filter="int" if numeric else None,
            size_hint=(None, None),
            pos_hint={"x": 0, "y": 0})
        self.add_widget(self.input)
        with self.canvas.before:
            Color(rgba=theme.LIGHT_GRAY)
            self._outline = RoundedRectangle(radius=[dp(8)])
            Color(rgba=(0, 0, 0, 0))
        self.bind(pos=self._layout, size=self._layout)
        self.input.bind(focus=self._focus)
        self._layout()

    def _layout(self, *_):
        field_h = dp(40)
        self.input.size = (self.width, field_h)
        # Outline: rounded rect drawn as two rects is overkill; use a Line.
        self._outline.pos = self.pos
        self._outline.size = (self.width, field_h)

    def _focus(self, _input, focus):
        self._redraw_outline()

    def set_error(self, error: bool):
        if error != self._error:
            self._error = error
            self._redraw_outline()

    def _redraw_outline(self):
        # Rebuild the outline with the state color as a stroked line.
        self.canvas.before.clear()
        with self.canvas.before:
            Color(rgba=(theme.STATUS_ERROR if self._error
                        else theme.OUTLINE_GRAY if self.input.focus
                        else theme.LIGHT_GRAY))
            Line(rounded_rectangle=(self.x, self.y, self.width, dp(40), dp(8)),
                 width=dp(1.2))
        self.bind(pos=lambda w, _: self._redraw_outline(),
                  size=lambda w, _: self._redraw_outline())


# -- the dialog ------------------------------------------------------------------


class PayContactDialog(FloatLayout):
    """PayContactContent as a full-screen overlay: scrim, card, fields and
    the contact-picker / permission sub-dialogs."""

    def __init__(self, on_dismiss, on_confirm, palette=None,
                 contact_provider=None, show_toast=None, **kwargs):
        super().__init__(**kwargs)
        self._palette = palette or theme.accent_theme_for(False)
        self._on_dismiss = on_dismiss
        self._on_confirm = on_confirm
        self._provider = (contact_provider if contact_provider is not None
                          else UnavailableContactProvider())
        self._show_toast = show_toast or (lambda _msg: None)
        self.state = PayContactState()
        self._picker = None
        self._permission_dialog = None

        self._scrim = _DialogScrim(self._dismiss, pos_hint={"x": 0, "y": 0})
        self.add_widget(self._scrim)

        self._anchor = AnchorLayout(pos_hint={"x": 0, "y": 0})
        self.add_widget(self._anchor)

        fields = BoxLayout(orientation="vertical", spacing=dp(12),
                           size_hint_y=None)
        fields.bind(minimum_height=fields.setter("height"))

        # Selected-contact card (only while a picker choice stands).
        self._recipient_card = FloatLayout(size_hint_y=None, height=0)
        fields.add_widget(self._recipient_card)

        phone_row = BoxLayout(orientation="horizontal", spacing=dp(8),
                              size_hint_y=None, height=dp(_Field.HEIGHT))
        self.phone_field = _Field(STR_MOBILE_LABEL, STR_MOBILE_HINT,
                                  self._palette, numeric=False)
        self.phone_field.input.bind(text=self._phone_changed)
        phone_row.add_widget(self.phone_field)
        pick_anchor = AnchorLayout(anchor_y="bottom", size_hint_x=None,
                                   width=dp(48))
        self._pick_button = _IconButton(
            (*self._palette.accent[:3], 0.2), "person", self._palette.accent,
            glyph_scale=0.55, radius=8, on_press=self.choose_contact,
            size_hint=(None, None), size=(dp(40), dp(40)))
        pick_anchor.add_widget(self._pick_button)
        phone_row.add_widget(pick_anchor)
        fields.add_widget(phone_row)

        self.amount_field = _Field(STR_AMOUNT_LABEL, STR_AMOUNT_HINT,
                                   self._palette, numeric=True)
        self.amount_field.input.bind(text=self._amount_changed)
        fields.add_widget(self.amount_field)

        self._cap_label = _left_label(
            message_for(Reason.AMOUNT_ABOVE_CAP), "12sp", theme.STATUS_ERROR)
        self._cap_label.size_hint_y = None
        self._cap_label.height = 0
        self._cap_label.opacity = 0
        self._cap_label.bind(width=lambda w, _: setattr(
            w, "text_size", (w.width, None)))
        fields.add_widget(self._cap_label)

        self._card = _DialogCard(
            STR_TITLE,
            actions=[
                (STR_CANCEL, theme.TEXT_LIGHT_GRAY, self._dismiss),
                (STR_TRANSFER, self._palette.accent, self._confirm),
            ],
            content=fields, palette=self._palette,
            width=dp(340), height=dp(300))
        self._anchor.add_widget(self._card)
        self._refresh_actions()

    # -- field wiring -----------------------------------------------------------

    def _phone_changed(self, _input, text):
        accepted = self.state.update_phone(text)
        if accepted != text:
            self.phone_field.input.text = accepted
            return
        self._refresh_recipient()
        self._refresh_actions()

    def _amount_changed(self, _input, text):
        # ContactAmountField: digits only, at most MAX_AMOUNT_INPUT_DIGITS.
        digits = "".join(c for c in text if c.isdigit())
        if len(digits) > MAX_AMOUNT_INPUT_DIGITS:
            digits = digits[:MAX_AMOUNT_INPUT_DIGITS]
        if digits != text:
            self.amount_field.input.text = digits
            return
        self.state.amount = digits
        over = self.state.is_over_cap
        self.amount_field.set_error(over)
        self._cap_label.opacity = 1 if over else 0
        self._cap_label.height = dp(32) if over else 0
        self._refresh_actions()

    def _refresh_recipient(self):
        name = self.state.selected_contact_name
        self._recipient_card.clear_widgets()
        self._recipient_card.height = dp(44) if name else 0
        if not name:
            return
        card = FloatLayout(pos_hint={"x": 0, "y": 0})
        with card.canvas.before:
            Color(rgba=(*self._palette.accent[:3], 0.15))
            card._bg = RoundedRectangle(radius=[dp(8)])
        card.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        row = BoxLayout(orientation="horizontal", spacing=dp(8),
                        padding=[dp(10), 0], pos_hint={"x": 0, "y": 0})
        row.add_widget(Glyph("person", self._palette.accent,
                             size_hint=(None, None), size=(dp(16), dp(16)),
                             pos_hint={"center_y": 0.5}))
        row.add_widget(_left_label(STR_RECIPIENT % name, "13sp",
                                   self._palette.accent))
        card.add_widget(row)
        self._recipient_card.add_widget(card)

    def _refresh_actions(self):
        # Transfer greys out (PayNetTextGray) until canTransfer holds.
        # Kivy children lists are reversed: the last-added action (Transfer)
        # is children[0] of the actions row.
        actions_row = self._card.children[0].children[0]
        transfer_link = actions_row.children[0]
        enabled = self.state.can_transfer
        transfer_link.color = (self._palette.accent if enabled
                               else theme.TEXT_GRAY)
        transfer_link.disabled = not enabled

    # -- actions -----------------------------------------------------------------

    def _dismiss(self, *_):
        self._on_dismiss()

    def _confirm(self, *_):
        if not self.state.can_transfer:
            return
        self._on_confirm(self.state.phone_number, self.state.amount,
                         self.state.selected_contact_name)

    # -- contact picker flow -------------------------------------------------------

    def choose_contact(self, *_):
        """ContactPickerFlow: provider missing -> toast; granted -> picker;
        otherwise the permission explanation."""
        if self._provider is None:
            self._show_toast(STR_NO_CONTACTS_ACCESS)
        elif self._provider.has_contact_permission():
            self._open_picker()
        else:
            self._open_permission_dialog()

    def _open_picker(self):
        if self._picker is None:
            self._picker = ContactPickerDialog(
                self._provider, self._palette,
                on_dismiss=self._close_picker,
                on_contact_selected=self._contact_selected)
            self.add_widget(self._picker)

    def _close_picker(self, *_):
        if self._picker is not None:
            self.remove_widget(self._picker)
            self._picker = None
        self.state.show_contact_picker = False

    def _contact_selected(self, contact):
        self.state.select_contact(contact.phone_number, contact.name)
        self.phone_field.input.text = contact.phone_number
        self._close_picker()
        self._refresh_recipient()
        self._refresh_actions()

    def _open_permission_dialog(self):
        if self._permission_dialog is None:
            self._permission_dialog = PermissionExplanationDialog(
                STR_CONTACTS_PERMISSION_TITLE, STR_CONTACTS_PERMISSION_BODY,
                STR_PERMISSION_CONTINUE, self._palette,
                on_confirm=self._permission_confirmed,
                on_dismiss=self._close_permission_dialog)
            self.add_widget(self._permission_dialog)

    def _close_permission_dialog(self, *_):
        if self._permission_dialog is not None:
            self.remove_widget(self._permission_dialog)
            self._permission_dialog = None
        self.state.show_contact_permission_dialog = False

    def _permission_confirmed(self, *_):
        self._close_permission_dialog()
        self._provider.request_contact_permission(
            lambda granted: self._open_picker() if granted else None)


class PermissionExplanationDialog(FloatLayout):
    """PermissionExplanationDialog: scrim, DarkGray card, message, accent
    confirm + Not-now dismiss."""

    def __init__(self, title, message, confirm_text, palette,
                 on_confirm, on_dismiss, **kwargs):
        super().__init__(**kwargs)
        self._scrim = _DialogScrim(on_dismiss, pos_hint={"x": 0, "y": 0})
        self.add_widget(self._scrim)
        anchor = AnchorLayout(pos_hint={"x": 0, "y": 0})
        self.add_widget(anchor)
        body = _left_label(message, "14sp", theme.TEXT_PALE)
        body.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
        anchor.add_widget(_DialogCard(
            title,
            actions=[
                (STR_NOT_NOW, theme.TEXT_LIGHT_GRAY, on_dismiss),
                (confirm_text, palette.accent, on_confirm),
            ],
            content=body, palette=palette,
            width=dp(340), height=dp(210)))


class _ContactRow(ButtonBehavior, FloatLayout):
    """ContactItem: MediumGray card, accent-tinted person disc, name +
    number."""

    HEIGHT = 68

    def __init__(self, contact, palette, on_press, **kwargs):
        super().__init__(**kwargs)
        self._on_press = on_press
        with self.canvas.before:
            Color(rgba=theme.MEDIUM_GRAY)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size,
                                        radius=[dp(8)])
        self.bind(pos=lambda *_: setattr(self._bg, "pos", self.pos),
                  size=lambda *_: setattr(self._bg, "size", self.size))
        row = BoxLayout(orientation="horizontal", spacing=dp(12),
                        padding=[dp(12), 0], pos_hint={"x": 0, "y": 0})
        self.add_widget(row)
        row.add_widget(_IconButton(
            (*palette.accent[:3], 0.2), "person", palette.accent,
            glyph_scale=0.6, size_hint=(None, None), size=(dp(40), dp(40)),
            pos_hint={"center_y": 0.5}))
        texts = BoxLayout(orientation="vertical", spacing=dp(2))
        texts.add_widget(_left_label(contact.name, "16sp", (1, 1, 1, 1)))
        texts.add_widget(_left_label(contact.phone_number, "14sp",
                                     theme.TEXT_LIGHT_GRAY))
        row.add_widget(texts)

    def on_release(self):
        self._on_press()


class ContactPickerDialog(FloatLayout):
    """ContactPickerDialog: searchable contact list with loading / failed /
    empty states. Contacts come from the injected provider."""

    def __init__(self, provider, palette, on_dismiss, on_contact_selected,
                 **kwargs):
        super().__init__(**kwargs)
        self._provider = provider
        self._palette = palette
        self._on_dismiss = on_dismiss
        self._on_contact_selected = on_contact_selected
        self._query = ""
        self._contacts: List[Contact] = []
        self._loading = True
        self._load_failed = False

        self._scrim = _DialogScrim(on_dismiss, pos_hint={"x": 0, "y": 0})
        self.add_widget(self._scrim)
        anchor = AnchorLayout(pos_hint={"x": 0, "y": 0})
        self.add_widget(anchor)
        self._card = FloatLayout(size_hint=(None, None),
                                 size=(dp(340), dp(480)))
        with self._card.canvas.before:
            Color(rgba=theme.DARK_GRAY)
            self._card._bg = RoundedRectangle(radius=[dp(20)])
        self._card.bind(
            pos=lambda w, _: setattr(w._bg, "pos", w.pos),
            size=lambda w, _: setattr(w._bg, "size", w.size))
        anchor.add_widget(self._card)

        col = BoxLayout(orientation="vertical", spacing=dp(12),
                        padding=[dp(20), dp(20)],
                        pos_hint={"x": 0, "y": 0})
        self._card.add_widget(col)
        title_row = BoxLayout(orientation="horizontal",
                              size_hint_y=None, height=dp(40))
        title_row.add_widget(_left_label(STR_CONTACTS_TITLE, "20sp",
                                         (1, 1, 1, 1), bold=True))
        close_anchor = AnchorLayout(size_hint_x=None, width=dp(40))
        close_anchor.add_widget(_IconButton(
            (0, 0, 0, 0), "close", theme.TEXT_LIGHT_GRAY, glyph_scale=0.5,
            on_press=self._dismiss, size_hint=(None, None),
            size=(dp(32), dp(32))))
        title_row.add_widget(close_anchor)
        col.add_widget(title_row)

        self._search = _Field("", STR_CONTACTS_SEARCH_HINT, self._palette)
        self._search.input.bind(text=self._query_changed)
        col.add_widget(self._search)

        self._body = FloatLayout()
        col.add_widget(self._body)
        self._load()
        self._rebuild_body()

    def _dismiss(self, *_):
        self._on_dismiss()

    def _query_changed(self, _input, text):
        self._query = text
        self._rebuild_body()

    def _load(self):
        self._loading = True
        self._load_failed = False
        try:
            self._contacts = self._provider.load_contacts()
        except Exception:
            self._load_failed = True
            self._contacts = []
        self._loading = False

    def _retry(self, *_):
        self._load()
        self._rebuild_body()

    def _rebuild_body(self):
        self._body.clear_widgets()
        anchor = AnchorLayout(pos_hint={"x": 0, "y": 0})
        self._body.add_widget(anchor)
        if self._loading:
            # DEVIATION: ellipsis label stands in for the
            # CircularProgressIndicator, as elsewhere in the port.
            anchor.add_widget(Label(text="…", font_size="28sp",
                                    color=self._palette.accent))
            return
        if self._load_failed:
            col = BoxLayout(orientation="vertical", spacing=dp(8),
                            size_hint=(None, None), size=(dp(240), dp(96)))
            col.add_widget(Label(text=STR_CONTACTS_FAILED, font_size="14sp",
                                 color=theme.ONBOARDING_SECONDARY,
                                 halign="center", size_hint_y=None,
                                 height=dp(40)))
            col.add_widget(_TextLink(STR_CONTACTS_RETRY, self._retry,
                                     font_size="14sp",
                                     color=self._palette.accent,
                                     halign="center",
                                     size_hint_y=None, height=dp(32)))
            anchor.add_widget(col)
            return
        filtered = filter_contacts(self._contacts, self._query)
        if not filtered:
            anchor.add_widget(Label(
                text=(STR_CONTACTS_EMPTY if not self._query.strip()
                      else STR_CONTACTS_NO_MATCHES),
                font_size="16sp", color=theme.ONBOARDING_SECONDARY))
            return
        self._body.remove_widget(anchor)
        scroll = ScrollView(pos_hint={"x": 0, "y": 0})
        inner = BoxLayout(orientation="vertical", spacing=dp(8),
                          size_hint_y=None)
        inner.bind(minimum_height=inner.setter("height"))
        for contact in filtered:
            inner.add_widget(_ContactRow(
                contact, self._palette,
                on_press=lambda c=contact: self._selected(c),
                size_hint_y=None, height=dp(_ContactRow.HEIGHT)))
        scroll.add_widget(inner)
        self._body.add_widget(scroll)

    def _selected(self, contact):
        self._on_contact_selected(contact)
