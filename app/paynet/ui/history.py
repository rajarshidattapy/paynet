# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/ui/activities/
# TransactionHistoryActivity.kt and app/src/main/java/com/paynet/app/ui/
# components/TransactionDetailDialog.kt (+ the OnboardingDialog pieces its
# delete confirmation reuses).

"""Transaction history screen and transaction detail receipt."""

import time

from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from paynet import theme
from paynet.db.models import Transaction
from paynet.ui.home import Glyph, _gradient_texture
from paynet.ui.home_legacy import _IconButton, _TextLink, _left_label, _white
from paynet.ui.presentation import historical_date_label, matches_search
from paynet.utils.currency import inr
from paynet.utils.dates import format_full_date, format_time

# -- strings.xml -------------------------------------------------------------
STR_TITLE = "Transactions"
STR_BACK = "Back"
STR_SEARCH = "Search"
STR_CLOSE_SEARCH = "Close search"
STR_CLEAR_SEARCH = "Clear search"
STR_SEARCH_PLACEHOLDER = "Search by name or number…"
STR_GROUP_TODAY = "Today"
STR_GROUP_YESTERDAY = "Yesterday"
STR_GROUP_THIS_WEEK = "This Week"
# These four are hardcoded in the Kotlin screen, not resources.
STR_ERROR_TITLE = "Something went wrong"
STR_RETRY = "Retry"
STR_EMPTY_SEARCH_TITLE = "No matching transactions"
STR_EMPTY_SEARCH_SUBTITLE = "Try a different search"
STR_EMPTY_TITLE = "No transactions yet"
STR_EMPTY_SUBTITLE = "Transactions will appear here"

STR_DETAIL_TITLE = "Transaction details"
STR_DETAIL_CLOSE = "Close"
STR_LABEL_RECIPIENT = "Recipient"
STR_LABEL_AMOUNT = "Amount"
STR_LABEL_PHONE = "Phone number"
STR_LABEL_UPI = "UPI ID"
STR_LABEL_BANK_REF = "Bank reference"
STR_LABEL_DATE_TIME = "Date & Time"
STR_RECIPIENT_UNKNOWN = "Not recorded"
STR_DONE = "Done"
STR_DELETE_RECORD = "Delete record"
STR_DELETE_CONFIRM_TITLE = "Delete this transaction?"
STR_DELETE_EXPLANATION = ("This removes the record from this device. It cannot "
                          "be undone and does not affect the actual payment.")
STR_CANCEL = "Cancel"

STATUS_LABELS = {
    "USER_CONFIRMED": "✓ Confirmed by you",
    "USER_NOT_CONFIRMED": "✕ Not confirmed by you",
    "UNVERIFIED": "Unverified",
    "NEEDS_REVIEW": "Check",
    "CANCELLED": "Cancelled",
}


def status_label(status: str) -> str:
    """statusLabelRes: the manual-confirmation labels outrank the bank ones."""
    s = (status or "").upper()
    if s in STATUS_LABELS:
        return STATUS_LABELS[s]
    if s in ("SUCCESS", "SUCCESSFUL", "COMPLETED"):
        return "Success"
    if s in ("FAILED", "DECLINED"):
        return "Failed"
    return "Pending"


def group_transactions(transactions, now_ms: int):
    """Group sorted-descending transactions into Today / Yesterday /
    This Week / historical-date sections, preserving encounter order
    (Kotlin linkedMapOf semantics)."""
    now = time.localtime(now_ms / 1000)
    yesterday = time.localtime((now_ms - 86_400_000) / 1000)
    week_ago_ms = now_ms - 7 * 86_400_000

    def same_day(a, b):
        return (a.tm_year, a.tm_yday) == (b.tm_year, b.tm_yday)

    grouped = {}
    for tx in sorted(transactions, key=lambda t: t.timestamp, reverse=True):
        tx_cal = time.localtime(tx.timestamp / 1000)
        if same_day(tx_cal, now):
            key = STR_GROUP_TODAY
        elif same_day(tx_cal, yesterday):
            key = STR_GROUP_YESTERDAY
        elif tx.timestamp > week_ago_ms:
            key = STR_GROUP_THIS_WEEK
        else:
            key = historical_date_label(tx.timestamp, now_ms)
        grouped.setdefault(key, []).append(tx)
    return grouped


# -- list rows ----------------------------------------------------------------


class StatusPill(FloatLayout):
    """11sp status text on a 15%-alpha tint, rounded 6."""

    def __init__(self, status: str, **kwargs):
        super().__init__(**kwargs)
        self.status = status
        color = theme.status_color(status)
        with self.canvas.before:
            Color(rgba=(color[0], color[1], color[2], 0.15))
            self._bg = RoundedRectangle(radius=[dp(6)])
        self.bind(pos=self._layout, size=self._layout)
        # size_hint=(None, None): the pill's layout must never resize the
        # label, or texture_size -> _fit -> do_layout -> texture_update
        # loops forever.
        self._label = Label(text=status_label(status), font_size="11sp",
                            color=color, size_hint=(None, None),
                            pos_hint={"x": 0, "y": 0})
        self.add_widget(self._label)
        self._label.bind(texture_size=self._fit)
        self._fit()

    def _fit(self, *_):
        tw, th = self._label.texture_size
        if tw <= 0 or th <= 0:
            return
        size = (tw + dp(16), th + dp(4))
        self.size_hint = (None, None)
        if tuple(self.size) != size:
            self.size = size
        if tuple(self._label.size) != (tw, th):
            self._label.size = (tw, th)
        self._layout()

    def _layout(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._label.center = self.center


class TransactionAvatar(FloatLayout):
    """40dp DarkGray circle with the recipient's initial."""

    def __init__(self, initial: str, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(rgba=theme.DARK_GRAY)
            # Explicit initial rect: the widget size arrives via kwargs
            # before the bind below exists, so an uninitialised Ellipse
            # would keep its default 100x100 forever.
            self._bg = Ellipse(pos=self.pos, size=self.size)
        self.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        self.add_widget(Label(text=initial, font_size="16sp", bold=True,
                              color=(1, 1, 1, 1), pos_hint={"x": 0, "y": 0}))


class HistoryRow(ButtonBehavior, FloatLayout):
    """TransactionHistoryItem: avatar, name + time, amount + status pill."""

    HEIGHT = 64  # 12dp vertical padding around a 40dp avatar

    def __init__(self, transaction: Transaction, on_press=None, **kwargs):
        super().__init__(**kwargs)
        self.transaction = transaction
        self._on_press = on_press
        display = transaction.recipient_label or STR_RECIPIENT_UNKNOWN
        initial = display[0].upper()

        row = BoxLayout(orientation="horizontal", spacing=dp(12),
                        padding=[0, dp(12)], pos_hint={"x": 0, "y": 0})
        self.add_widget(row)
        row.add_widget(TransactionAvatar(initial, size_hint=(None, None),
                                         size=(dp(40), dp(40))))
        name_col = BoxLayout(orientation="vertical", spacing=dp(2))
        name_col.add_widget(_left_label(display, "15sp", (1, 1, 1, 1)))
        name_col.add_widget(_left_label(format_time(transaction.timestamp),
                                        "13sp", theme.TEXT_LIGHT_GRAY))
        row.add_widget(name_col)
        right = BoxLayout(orientation="vertical", spacing=dp(4),
                          size_hint_x=None, width=dp(150))
        if (transaction.amount or "").strip():
            amount = _left_label("₹" + inr(transaction.amount), "16sp",
                                 (1, 1, 1, 1), bold=True)
            amount.halign = "right"
            right.add_widget(amount)
        pill_anchor = AnchorLayout(anchor_x="right", size_hint_y=None,
                                   height=dp(20))
        pill_anchor.add_widget(StatusPill(transaction.status))
        right.add_widget(pill_anchor)
        row.add_widget(right)

    def on_release(self):
        if self._on_press is not None:
            self._on_press(self.transaction)


class _Divider(Widget):
    """HorizontalDivider: 0.5dp line, indented 52dp from the start."""

    def __init__(self, color, indent=52, **kwargs):
        super().__init__(size_hint_y=None, height=dp(0.5), **kwargs)
        self._indent = indent
        with self.canvas:
            Color(rgba=color)
            self._line = Line(points=[], width=dp(0.5))
        self.bind(pos=self._draw, size=self._draw)
        self._draw()

    def _draw(self, *_):
        self._line.points = [self.x + dp(self._indent), self.y,
                             self.right, self.y]


# -- header + search ----------------------------------------------------------


class HistoryHeaderCard(FloatLayout):
    """Compact gradient header: back, title, search toggle."""

    HEIGHT = 96  # 8dp outer vertical padding + 16+48+16 card padding

    def __init__(self, palette, on_back, on_toggle_search, **kwargs):
        super().__init__(**kwargs)
        gradient = _gradient_texture(palette.header_gradient_start,
                                     palette.header_gradient_end)
        card = FloatLayout(size_hint=(None, None), height=dp(80),
                           pos_hint={"x": 0, "center_y": 0.5})
        with card.canvas.before:
            Color(rgba=(1, 1, 1, 1))
            card._bg = RoundedRectangle(radius=[dp(20)])
            card._bg.texture = gradient
        card.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        self.add_widget(card)
        self._card = card
        self.bind(size=lambda w, _: setattr(w._card, "width", w.width - dp(32)))

        row = BoxLayout(orientation="horizontal", spacing=dp(12),
                        padding=[dp(16), dp(16)],
                        pos_hint={"x": 0, "y": 0})
        card.add_widget(row)
        self.back_button = _IconButton(
            _white(0.22), "back", palette.on_accent, glyph_scale=0.55,
            on_press=on_back, size_hint=(None, None), size=(dp(36), dp(36)))
        back_anchor = AnchorLayout(size_hint_x=None, width=dp(48))
        back_anchor.add_widget(self.back_button)
        row.add_widget(back_anchor)
        row.add_widget(_left_label(STR_TITLE, "20sp", palette.on_accent,
                                   bold=True))
        self.search_button = _IconButton(
            _white(0.22), "search", palette.on_accent, glyph_scale=0.55,
            on_press=on_toggle_search, size_hint=(None, None),
            size=(dp(36), dp(36)))
        search_anchor = AnchorLayout(size_hint_x=None, width=dp(48))
        search_anchor.add_widget(self.search_button)
        row.add_widget(search_anchor)

    def set_search_open(self, open_: bool):
        # White alpha 0.35 while open, 0.22 while closed.
        self.search_button._bg = _white(0.35 if open_ else 0.22)
        self.search_button.glyph._kind = "close" if open_ else "search"
        self.search_button.glyph._draw()


class SearchBar(FloatLayout):
    """OutlinedTextField port: rounded-16 DarkGray field with leading
    search glyph and a trailing clear action while the query is non-empty."""

    HEIGHT = 64  # 56dp field + 8dp bottom padding

    def __init__(self, on_query, **kwargs):
        super().__init__(**kwargs)
        self._on_query = on_query
        field = FloatLayout(size_hint=(None, None), height=dp(56),
                            pos_hint={"x": 0, "center_y": 0.5})
        with field.canvas.before:
            Color(rgba=theme.DARK_GRAY)
            field._bg = RoundedRectangle(radius=[dp(16)])
        field.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                   size=lambda w, _: setattr(w._bg, "size", w.size))
        self.add_widget(field)
        self._field = field
        self.bind(size=lambda w, _: setattr(w._field, "width",
                                            w.width - dp(32)))

        row = BoxLayout(orientation="horizontal", spacing=dp(8),
                        padding=[dp(14), 0, dp(6), 0],
                        pos_hint={"x": 0, "y": 0})
        field.add_widget(row)
        row.add_widget(Glyph("search", theme.TEXT_LIGHT_GRAY,
                             size_hint=(None, None), size=(dp(20), dp(20)),
                             pos_hint={"center_y": 0.5}))
        self.input = TextInput(text="", hint_text=STR_SEARCH_PLACEHOLDER,
                               hint_text_color=theme.TEXT_LIGHT_GRAY,
                               foreground_color=(1, 1, 1, 1),
                               cursor_color=(1, 1, 1, 1), font_size="14sp",
                               background_color=(0, 0, 0, 0),
                               background_normal="", background_active="",
                               multiline=False,
                               padding=[0, dp(17), 0, 0])
        self.input.bind(text=self._query_changed)
        row.add_widget(self.input)
        self.clear_button = _IconButton(
            (0, 0, 0, 0), "close", theme.TEXT_LIGHT_GRAY, glyph_scale=0.5,
            on_press=self._clear, size_hint=(None, None),
            size=(dp(28), dp(28)), pos_hint={"center_y": 0.5})
        self.clear_button.opacity = 0
        self.clear_button.disabled = True
        row.add_widget(self.clear_button)

    def _query_changed(self, _input, text):
        has = bool(text)
        self.clear_button.opacity = 1 if has else 0
        self.clear_button.disabled = not has
        self._on_query(text)

    def _clear(self, *_):
        self.input.text = ""

    def reset(self):
        self.input.text = ""


# -- the screen ----------------------------------------------------------------


class HistoryScreen(FloatLayout):
    """TransactionHistoryScreen: black canvas, centered 420dp-max column,
    gradient header, toggleable search, grouped transaction list."""

    MAX_CONTENT_WIDTH = 420

    def __init__(self, view_model, palette=None, on_back=None,
                 on_delete=None, **kwargs):
        super().__init__(**kwargs)
        self._vm = view_model
        self._palette = palette or theme.accent_theme_for(False)
        self._on_back = on_back or (lambda: None)
        self._on_delete = on_delete
        self._query = ""
        self._search_open = False
        self._detail = None
        self._snackbar = None

        with self.canvas.before:
            Color(rgba=(0, 0, 0, 1))
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda *_: setattr(self._bg_rect, "pos", self.pos),
                  size=lambda *_: setattr(self._bg_rect, "size", self.size))

        self._column = BoxLayout(orientation="vertical", spacing=0,
                                 size_hint=(None, None))
        self.add_widget(self._column)

        self._column.add_widget(Widget(size_hint_y=None, height=dp(8)))
        self.header = HistoryHeaderCard(
            self._palette, self._on_back, self._toggle_search,
            size_hint_y=None, height=dp(HistoryHeaderCard.HEIGHT))
        self._column.add_widget(self.header)
        self._column.add_widget(Widget(size_hint_y=None, height=dp(8)))

        self.search_bar = SearchBar(self._query_changed,
                                    size_hint_y=None, height=0)
        self.search_bar.opacity = 0
        self._column.add_widget(self.search_bar)

        self._content = FloatLayout()
        self._column.add_widget(self._content)

        self.bind(size=self._relayout, pos=self._relayout)
        self._relayout()
        self._vm.history_state.subscribe(lambda _state: self._apply_state())
        self._vm.error.subscribe(self._on_error)
        self._apply_state()

    # -- layout ---------------------------------------------------------------

    def _relayout(self, *_):
        w, h = self.size
        if w <= 0 or h <= 0:
            return
        self._column.width = min(w, dp(self.MAX_CONTENT_WIDTH))
        self._column.height = h
        self._column.center_x = self.center_x
        self._column.y = self.y

    # -- search ---------------------------------------------------------------

    def _toggle_search(self):
        if self._search_open:
            # Kotlin: closing the bar also clears the query + focus.
            self.search_bar.reset()
            self._query = ""
        self._search_open = not self._search_open
        self.header.set_search_open(self._search_open)
        # AnimatedVisibility collapses to zero height; the port swaps height.
        self.search_bar.height = dp(SearchBar.HEIGHT) if self._search_open else 0
        self.search_bar.opacity = 1 if self._search_open else 0
        self._rebuild()

    def _query_changed(self, text):
        self._query = text
        self._rebuild()

    # -- states ---------------------------------------------------------------

    def _clear_content(self):
        self._content.clear_widgets()

    def _center_column(self):
        anchor = AnchorLayout(pos_hint={"x": 0, "y": 0})
        anchor.size = self._content.size
        self._content.bind(size=lambda _c, s: setattr(anchor, "size", s))
        col = BoxLayout(orientation="vertical", spacing=dp(6),
                        size_hint=(None, None), size=(dp(280), dp(180)))
        anchor.add_widget(col)
        self._content.add_widget(anchor)
        return col

    def _state_icon(self, ink):
        holder = AnchorLayout(size_hint_y=None, height=dp(64))
        circle = Widget(size_hint=(None, None), size=(dp(64), dp(64)))
        with circle.canvas.before:
            Color(rgba=theme.MEDIUM_GRAY)
            circle._bg = Ellipse(pos=circle.pos, size=circle.size)
        circle.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                    size=lambda w, _: setattr(w._bg, "size", w.size))
        glyph = Glyph("history", ink, size_hint=(None, None),
                      size=(dp(32), dp(32)))
        circle.add_widget(glyph)
        glyph.center = circle.center
        circle.bind(center=lambda w, _: setattr(glyph, "center", w.center))
        holder.add_widget(circle)
        return holder

    def _show_loading(self):
        self._clear_content()
        col = self._center_column()
        # DEVIATION: an ellipsis label stands in for the
        # CircularProgressIndicator, as on the home dashboards.
        col.add_widget(Label(text="…", font_size="28sp",
                             color=self._palette.header_gradient_start,
                             size_hint_y=None, height=dp(52)))

    def _show_error(self):
        self._clear_content()
        col = self._center_column()
        col.add_widget(self._state_icon(theme.STATUS_ERROR))
        col.add_widget(Label(text=STR_ERROR_TITLE, font_size="16sp", bold=True,
                             color=(1, 1, 1, 1), size_hint_y=None,
                             height=dp(26)))
        retry = AnchorLayout(size_hint_y=None, height=dp(40))
        retry.add_widget(_TextLink(
            STR_RETRY, lambda *_: self._vm.retry_history(),
            font_size="14sp", bold=True, color=self._palette.primary,
            size_hint=(None, None), size=(dp(60), dp(40)), halign="center"))
        col.add_widget(retry)

    def _show_empty(self):
        self._clear_content()
        col = self._center_column()
        col.add_widget(self._state_icon(theme.TEXT_LIGHT_GRAY))
        searching = bool(self._query.strip())
        col.add_widget(Label(
            text=STR_EMPTY_SEARCH_TITLE if searching else STR_EMPTY_TITLE,
            font_size="16sp", bold=True, color=(1, 1, 1, 1),
            size_hint_y=None, height=dp(26)))
        col.add_widget(Label(
            text=STR_EMPTY_SEARCH_SUBTITLE if searching else STR_EMPTY_SUBTITLE,
            font_size="13sp", color=theme.TEXT_LIGHT_GRAY,
            size_hint_y=None, height=dp(22)))

    def _show_list(self, transactions):
        self._clear_content()
        scroll = ScrollView(pos_hint={"x": 0, "y": 0},
                            do_scroll_x=False, do_scroll_y=True)
        inner = BoxLayout(orientation="vertical", spacing=0,
                          size_hint_y=None,
                          padding=[dp(16), 0, dp(16), dp(24)])
        inner.bind(minimum_height=inner.setter("height"))
        grouped = group_transactions(transactions, int(time.time() * 1000))
        for label, txs in grouped.items():
            header = _left_label(label, "12sp", theme.TEXT_LIGHT_GRAY,
                                 bold=True)
            header.size_hint_y = None
            header.height = dp(16) + dp(8) + dp(18)
            header.valign = "bottom"
            header.bind(size=lambda w, _: setattr(w, "text_size", w.size))
            inner.add_widget(header)
            for index, tx in enumerate(txs):
                inner.add_widget(HistoryRow(
                    tx, on_press=self._open_detail,
                    size_hint_y=None, height=dp(HistoryRow.HEIGHT)))
                if index < len(txs) - 1:
                    inner.add_widget(_Divider(theme.DARK_GRAY))
        scroll.add_widget(inner)
        self._content.add_widget(scroll)

    def _rebuild(self):
        state = self._vm.history_state.value
        self._apply_state(state)

    def _apply_state(self, state=None):
        state = state or self._vm.history_state.value
        if state.is_loading:
            self._show_loading()
        elif state.error is not None:
            self._show_error()
        else:
            filtered = [t for t in state.transactions
                        if matches_search(t, self._query)]
            if not filtered:
                self._show_empty()
            else:
                self._show_list(filtered)
        self._bring_detail_to_front()

    # -- detail dialog ----------------------------------------------------------

    def _open_detail(self, transaction):
        self._detail = TransactionDetailView(
            transaction, self._palette,
            on_dismiss=self._close_detail,
            on_delete=self._delete_and_close)
        self._detail.size = self.size
        self._detail.pos = self.pos
        self.add_widget(self._detail)

    def _close_detail(self, *_):
        if self._detail is not None:
            self.remove_widget(self._detail)
            self._detail = None

    def _delete_and_close(self, transaction):
        if self._on_delete is not None:
            self._on_delete(transaction)
        self._close_detail()

    def _bring_detail_to_front(self):
        if self._detail is not None:
            self.remove_widget(self._detail)
            self.add_widget(self._detail)

    # -- snackbar (action errors) ------------------------------------------------

    def _on_error(self, message):
        if not message:
            return
        # SnackbarHost port: transient bottom bar, then the error clears.
        if self._snackbar is not None:
            self.remove_widget(self._snackbar)
        bar = FloatLayout(size_hint=(None, None), height=dp(48),
                          pos_hint={"x": 0, "y": 0})
        with bar.canvas.before:
            Color(rgba=theme.MEDIUM_GRAY)
            bar._bg = RoundedRectangle(radius=[dp(12)])
        bar.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                 size=lambda w, _: setattr(w._bg, "size", w.size))
        bar.add_widget(Label(text=message, font_size="14sp",
                             color=(1, 1, 1, 1), pos_hint={"x": 0, "y": 0}))
        self._snackbar = bar
        self.add_widget(bar)
        self._place_snackbar()
        self._vm.clear_error()
        Clock.schedule_once(self._dismiss_snackbar, 3)

    def _place_snackbar(self, *_):
        if self._snackbar is None:
            return
        self._snackbar.width = self.width - dp(32)
        self._snackbar.center_x = self.center_x
        self._snackbar.y = self.y + dp(16)

    def _dismiss_snackbar(self, *_):
        if self._snackbar is not None:
            self.remove_widget(self._snackbar)
            self._snackbar = None


# -- transaction detail receipt -------------------------------------------------


class _DetailRow(ButtonBehavior, FloatLayout):
    """DetailRow: icon, label + value, copy action on the row's trailing
    icon button (the copy target is the value, as in Kotlin)."""

    MIN_HEIGHT = 76

    def __init__(self, icon_kind, label, value, palette, on_copy=None, **kwargs):
        super().__init__(**kwargs)
        self._on_copy = on_copy
        row = BoxLayout(orientation="horizontal", spacing=dp(12),
                        padding=[dp(18), dp(14)],
                        pos_hint={"x": 0, "y": 0})
        self.add_widget(row)
        icon_anchor = AnchorLayout(size_hint_x=None, width=dp(22))
        icon_anchor.add_widget(Glyph(icon_kind, palette.primary,
                                     size_hint=(None, None),
                                     size=(dp(22), dp(22))))
        row.add_widget(icon_anchor)
        texts = BoxLayout(orientation="vertical", spacing=dp(4))
        texts.add_widget(_left_label(label, "17sp", (1, 1, 1, 1)))
        texts.add_widget(_left_label(value, "13sp",
                                     theme.ONBOARDING_SECONDARY))
        row.add_widget(texts)
        copy_anchor = AnchorLayout(size_hint_x=None, width=dp(48))
        copy_anchor.add_widget(_IconButton(
            (0, 0, 0, 0), "copy", theme.ONBOARDING_SECONDARY, glyph_scale=0.4,
            on_press=self._copy, size_hint=(None, None),
            size=(dp(36), dp(36))))
        row.add_widget(copy_anchor)

    def _copy(self, *_):
        if self._on_copy is not None:
            self._on_copy()

    def on_release(self):
        # Kotlin's row itself is not clickable; only the copy icon is.
        pass


def copy_to_clipboard(value: str) -> None:
    try:
        from kivy.core.clipboard import Clipboard

        Clipboard.copy(value)
    except Exception:  # headless / no clipboard provider
        pass


class TransactionDetailView(FloatLayout):
    """TransactionDetailDialog: full-screen black receipt surface with the
    fields card, Done action, optional delete flow and a top-start back."""

    def __init__(self, transaction: Transaction, palette=None,
                 on_dismiss=None, on_delete=None, **kwargs):
        super().__init__(**kwargs)
        self.transaction = transaction
        self._palette = palette or theme.accent_theme_for(False)
        self._on_dismiss = on_dismiss or (lambda: None)
        self._on_delete = on_delete
        self._confirm = None

        with self.canvas.before:
            Color(rgba=(0, 0, 0, 1))
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda *_: setattr(self._bg_rect, "pos", self.pos),
                  size=lambda *_: setattr(self._bg_rect, "size", self.size))

        scroll = ScrollView(pos_hint={"x": 0, "y": 0})
        col = BoxLayout(orientation="vertical", spacing=0,
                        size_hint_y=None, padding=[dp(24), dp(48)])
        col.bind(minimum_height=col.setter("height"))
        scroll.add_widget(col)
        self.add_widget(scroll)

        icon_anchor = AnchorLayout(size_hint_y=None, height=dp(56))
        icon_anchor.add_widget(Glyph("receipt", self._palette.primary,
                                     size_hint=(None, None),
                                     size=(dp(48), dp(48))))
        col.add_widget(icon_anchor)
        col.add_widget(Widget(size_hint_y=None, height=dp(16)))
        title = Label(text=STR_DETAIL_TITLE, font_size="31sp", bold=True,
                      color=(1, 1, 1, 1), halign="center",
                      size_hint_y=None, height=dp(44))
        title.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
        col.add_widget(title)
        col.add_widget(Widget(size_hint_y=None, height=dp(28)))

        # The fields card.
        fields = self._fields()
        card = FloatLayout(size_hint_y=None,
                           height=dp(_DetailRow.MIN_HEIGHT) * len(fields))
        with card.canvas.before:
            Color(rgba=theme.ONBOARDING_SURFACE)
            card._bg = RoundedRectangle(radius=[dp(22)])
        card.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        card_col = BoxLayout(orientation="vertical", spacing=0,
                             pos_hint={"x": 0, "y": 0})
        card.add_widget(card_col)
        for index, (kind, label, value) in enumerate(fields):
            card_col.add_widget(_DetailRow(
                kind, label, value, self._palette,
                on_copy=lambda v=value: copy_to_clipboard(v),
                size_hint_y=None, height=dp(_DetailRow.MIN_HEIGHT)))
            if index < len(fields) - 1:
                card_col.add_widget(_Divider(_white(0.10)))
        col.add_widget(card)
        col.add_widget(Widget(size_hint_y=None, height=dp(24)))

        col.add_widget(_DialogAction(STR_DONE, self._palette,
                                     self._dismiss,
                                     size_hint_y=None, height=dp(52)))
        if self._on_delete is not None:
            col.add_widget(Widget(size_hint_y=None, height=dp(4)))
            delete_btn = _TextLink(STR_DELETE_RECORD, self._ask_delete,
                                   font_size="14sp",
                                   color=theme.STATUS_ERROR,
                                   halign="center",
                                   size_hint_y=None, height=dp(48))
            col.add_widget(delete_btn)

        back_anchor = AnchorLayout(anchor_x="left", anchor_y="top",
                                   size_hint=(None, None),
                                   size=(dp(60), dp(60)),
                                   pos_hint={"x": 0, "top": 1})
        back_anchor.add_widget(_IconButton(
            (0, 0, 0, 0), "back", self._palette.accent, glyph_scale=0.5,
            on_press=self._dismiss, size_hint=(None, None),
            size=(dp(40), dp(40))))
        self.add_widget(back_anchor)

    def _fields(self):
        tx = self.transaction
        fields = [
            ("person", STR_LABEL_RECIPIENT,
             tx.recipient_label or STR_RECIPIENT_UNKNOWN),
        ]
        # Unknown amounts stay absent, rather than becoming a lone symbol.
        if (tx.amount or "").strip():
            fields.append(("payments", STR_LABEL_AMOUNT,
                           "₹" + inr(tx.amount)))
        if (tx.phoneNumber or "").strip():
            fields.append(("phone", STR_LABEL_PHONE, tx.phoneNumber.strip()))
        if (tx.upiId or "").strip():
            fields.append(("at", STR_LABEL_UPI, tx.upiId.strip()))
        if (tx.bankRef or "").strip():
            fields.append(("tag", STR_LABEL_BANK_REF, tx.bankRef.strip()))
        # Icons.Outlined.Schedule is a clock, same shape as "history".
        fields.append(("history", STR_LABEL_DATE_TIME,
                       format_full_date(tx.timestamp)))
        return fields

    def _dismiss(self, *_):
        self._on_dismiss()

    def _ask_delete(self, *_):
        if self._confirm is None:
            self._confirm = DeleteConfirmView(
                self._palette,
                on_cancel=self._cancel_delete,
                on_delete=self._confirm_delete)
            self.add_widget(self._confirm)

    def _cancel_delete(self, *_):
        if self._confirm is not None:
            self.remove_widget(self._confirm)
            self._confirm = None

    def _confirm_delete(self, *_):
        self._cancel_delete()
        if self._on_delete is not None:
            self._on_delete(self.transaction)


class _DialogAction(ButtonBehavior, FloatLayout):
    """OnboardingDialogAction (primary): filled primaryDark rounded-14
    button, 16sp semibold onPrimaryDark text."""

    def __init__(self, text, palette, on_press=None, **kwargs):
        super().__init__(**kwargs)
        self._on_press = on_press
        with self.canvas.before:
            Color(rgba=palette.primary_dark)
            self._bg = RoundedRectangle(radius=[dp(14)])
        self.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        self.add_widget(Label(text=text, font_size="16sp", bold=True,
                              color=palette.on_primary_dark,
                              pos_hint={"x": 0, "y": 0}))

    def on_release(self):
        if self._on_press is not None:
            self._on_press()


class DeleteConfirmView(FloatLayout):
    """DeleteTransactionDialog: dimmed scrim, centered OnboardingSurface
    card, destructive action plus a filled cancel."""

    def __init__(self, palette, on_cancel, on_delete, **kwargs):
        super().__init__(**kwargs)
        self._on_cancel = on_cancel
        self._on_delete = on_delete
        with self.canvas.before:
            Color(rgba=(0, 0, 0, 0.6))
            self._scrim = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda *_: setattr(self._scrim, "pos", self.pos),
                  size=lambda *_: setattr(self._scrim, "size", self.size))

        anchor = AnchorLayout(pos_hint={"x": 0, "y": 0})
        self.add_widget(anchor)
        card = FloatLayout(size_hint=(None, None),
                           size=(min(self.width, dp(400)), dp(300)))
        self.bind(size=lambda w, _: setattr(
            card, "size", (min(w.width - dp(48), dp(400)), dp(300))))
        with card.canvas.before:
            Color(rgba=theme.ONBOARDING_SURFACE)
            card._bg = RoundedRectangle(radius=[dp(24)])
        card.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        anchor.add_widget(card)

        col = BoxLayout(orientation="vertical", spacing=dp(8),
                        padding=[dp(24), dp(24)],
                        pos_hint={"x": 0, "y": 0})
        card.add_widget(col)
        heading = BoxLayout(orientation="horizontal",
                            size_hint_y=None, height=dp(48))
        heading.add_widget(_left_label(STR_DELETE_CONFIRM_TITLE, "20sp",
                                       (1, 1, 1, 1), bold=True))
        close_anchor = AnchorLayout(size_hint_x=None, width=dp(48))
        close_anchor.add_widget(_IconButton(
            (0, 0, 0, 0), "close", theme.TEXT_LIGHT_GRAY, glyph_scale=0.5,
            on_press=self._cancel, size_hint=(None, None),
            size=(dp(36), dp(36))))
        heading.add_widget(close_anchor)
        col.add_widget(heading)
        message = _left_label(STR_DELETE_EXPLANATION, "15sp",
                              theme.TEXT_LIGHT_GRAY)
        message.bind(width=lambda w, _: setattr(w, "text_size",
                                                (w.width, None)))
        col.add_widget(message)
        col.add_widget(_TextLink(STR_DELETE_RECORD, self._delete,
                                 font_size="16sp", color=theme.STATUS_ERROR,
                                 halign="center",
                                 size_hint_y=None, height=dp(48)))
        col.add_widget(_DialogAction(STR_CANCEL, palette, self._cancel,
                                     size_hint_y=None, height=dp(52)))

    def _cancel(self, *_):
        self._on_cancel()

    def _delete(self, *_):
        self._on_delete()
