# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/ui/activities/PaymentResultActivity.kt

"""Payment result screen: the outcome the bank actually reported, for every
parsed confirmation, not only successes.

Color language (verbatim from the Kotlin comment): SUCCESS wears the brand
look (accent circle, white heading/amount). Non-success outcomes wear their
status color on circle + glyph so a FAILED result can never be mistaken for
a success at a glance. The glyph is always readable against the surface.

DEVIATIONS (recorded in MIGRATION.md): immersive system-UI handling and the
back dispatcher are platform concerns (feature 17); the entry animation uses
Kivy Animation with the same stagger/duration; the detector lookup for the
UPI_123 fallback recipient is injected.
"""

from datetime import datetime
from typing import Optional, Tuple

from kivy.animation import Animation
from kivy.graphics import Color as KvColor, Ellipse, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

from paynet import theme
from paynet import status as TransactionStatus
from paynet.ui.home import Glyph, _gradient_texture
from paynet.utils.currency import inr

RGB_MASK = 0x00FFFFFF
ICON_SURFACE_ALPHA = 0x24
BUTTON_RADIUS_DP = 16
ENTRY_OFFSET_DP = 8
ENTRY_STAGGER_MS = 24
ENTRY_DURATION_MS = 240

STATUS_TITLES = {
    TransactionStatus.FAILED: "Payment Failed",
    TransactionStatus.NEEDS_REVIEW: "Check This Payment",
    TransactionStatus.SUCCESS: "Payment Successful",
}
STATUS_EXPLAINERS = {
    TransactionStatus.FAILED: ("Your bank reported this payment as failed. "
                               "Any debited amount is normally auto-reversed."),
    TransactionStatus.NEEDS_REVIEW: "Check your bank statement before retrying.",
}
UNVERIFIED_TITLE = "No Confirmation Received"
UNVERIFIED_EXPLAINER = ("The outcome is unknown. Check with your bank or "
                        "recipient before retrying.")

RECIPIENT_PAID_TO = "Paid to"
RECIPIENT_RECEIVED_FROM = "Received from"
RECIPIENT_TO = "To"
RECIPIENT_FROM = "From"


def bank_reference_of(transaction_id: str) -> str:
    """The part of a stored transaction id a user can act on: ids are stored
    as `<bank reference>_<timestamp>`; generated ids (no separator) show
    as-is."""
    head, sep, _ = transaction_id.rpartition("_")
    return head if sep and head else transaction_id


def counterparty_label_for(status: str, transaction_type: str) -> str:
    """"Paid to"/"Received from" are past tense: only a confirmed SUCCESS
    earns them. Everything else names the counterparty without claiming an
    outcome."""
    is_credit = transaction_type == "CREDIT"
    if status != TransactionStatus.SUCCESS:
        return RECIPIENT_FROM if is_credit else RECIPIENT_TO
    return RECIPIENT_RECEIVED_FROM if is_credit else RECIPIENT_PAID_TO


def recipient_row(recipient_name: Optional[str], phone_number: Optional[str],
                  operation_type: str, detector_phone: Optional[str],
                  status: str, transaction_type: str) -> Optional[Tuple[str, str]]:
    if recipient_name:
        return counterparty_label_for(status, transaction_type), recipient_name
    if phone_number:
        return (RECIPIENT_FROM if transaction_type == "CREDIT" else RECIPIENT_TO), phone_number
    if operation_type == "UPI_123" and detector_phone:
        return RECIPIENT_TO, detector_phone
    return None


def result_presentation(status: str, accent_primary) -> dict:
    """title, optional explainer, glyph kind and accent for the outcome.
    Only an explicit SUCCESS earns the success styling; anything else —
    UNVERIFIED or unexpected — renders neutral, never the success look."""
    if status == TransactionStatus.SUCCESS:
        return {"title": STATUS_TITLES[TransactionStatus.SUCCESS],
                "explainer": None, "glyph": "check", "accent": accent_primary}
    if status == TransactionStatus.FAILED:
        return {"title": STATUS_TITLES[TransactionStatus.FAILED],
                "explainer": STATUS_EXPLAINERS[TransactionStatus.FAILED],
                "glyph": "error", "accent": theme.STATUS_ERROR}
    if status == TransactionStatus.NEEDS_REVIEW:
        return {"title": STATUS_TITLES[TransactionStatus.NEEDS_REVIEW],
                "explainer": STATUS_EXPLAINERS[TransactionStatus.NEEDS_REVIEW],
                "glyph": "error", "accent": theme.STATUS_WARNING}
    return {"title": UNVERIFIED_TITLE, "explainer": UNVERIFIED_EXPLAINER,
            "glyph": "unverified", "accent": theme.STATUS_NEUTRAL}


def format_result_datetime(timestamp_ms: int) -> str:
    """SimpleDateFormat("dd MMM yyyy, hh:mm a", Locale.getDefault())."""
    return datetime.fromtimestamp(timestamp_ms / 1000).strftime("%d %b %Y, %I:%M %p")


def format_result_amount(amount: str) -> str:
    return f"₹{inr(amount)}"


class PaymentResultScreen(FloatLayout):
    """activity_payment_success as a screen. re-render() is the onNewIntent
    path: a newer outcome replaces the stale one cleanly."""

    def __init__(self, accent=None, on_done=None, detector_phone=lambda: None,
                 operation_type=lambda: "", animations_enabled=True, **kwargs):
        kwargs.setdefault("size_hint", (1, 1))
        super().__init__(**kwargs)
        self._accent_theme = accent or theme.VIOLET_ACCENT_THEME
        self._on_done = on_done or (lambda: None)
        self._detector_phone = detector_phone
        self._operation_type = operation_type
        self._animations_enabled = animations_enabled
        with self.canvas.before:
            KvColor(0, 0, 0, 1)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[0])
        self.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        self._stage = BoxLayout(orientation="vertical", size_hint=(1, None),
                                spacing=0, padding=(dp(24), 0, dp(24), 0))
        self._stage.bind(minimum_height=self._stage.setter("height"))
        self.add_widget(self._stage)
        self.bind(size=self._center_stage, pos=self._center_stage)
        self._stage.bind(minimum_height=self._center_stage)

    def _center_stage(self, *_):
        self._stage.width = self.width
        self._stage.center_x = self.center_x
        self._stage.center_y = self.center_y

    # -- rendering -----------------------------------------------------------

    def render(self, transaction_id="N/A", amount="0", status="UNKNOWN",
               bank_name="Bank", timestamp_ms=None, upi_id=None,
               transaction_type="DEBIT", recipient_name=None,
               phone_number=None):
        """loadTransactionData + startAnimations: every property is set
        explicitly so a re-render from a different status resets cleanly."""
        presentation = result_presentation(status, self._accent_theme.primary)
        self._stage.clear_widgets()
        self._animated = []

        self._stage.add_widget(self._circle(presentation))
        self._stage.add_widget(_spacer(20))
        self._stage.add_widget(self._fade_in(Label(
            text=presentation["title"], font_size="24sp", bold=True,
            color=theme.TEXT_WHITE, size_hint=(1, None), halign="center",
            height=dp(34))))
        explainer = presentation["explainer"]
        if explainer is not None:
            self._stage.add_widget(_spacer(8))
            body = Label(text=explainer, font_size="14sp",
                         color=theme.ONBOARDING_SECONDARY, size_hint=(1, None),
                         halign="center")
            body.line_height = 20 / 14
            body.bind(width=lambda w, _: setattr(w, "text_size", (w.width - dp(64), None)),
                      texture_size=lambda w, s: setattr(w, "height", s[1]))
            self._stage.add_widget(self._fade_in(body))
        self._stage.add_widget(_spacer(12))
        self._stage.add_widget(self._fade_in(Label(
            text=format_result_amount(amount), font_size="34sp", bold=True,
            color=theme.TEXT_WHITE, size_hint=(1, None), halign="center",
            height=dp(44))))
        self._stage.add_widget(_spacer(20))
        self._stage.add_widget(self._fade_in(self._details_card(
            bank_name, bank_reference_of(transaction_id),
            format_result_datetime(timestamp_ms if timestamp_ms is not None else 0),
            upi_id, recipient_row(recipient_name, phone_number,
                                  self._operation_type(), self._detector_phone(),
                                  status, transaction_type))))
        self._stage.add_widget(_spacer(24))
        self._stage.add_widget(self._fade_in(self._done_button()))
        self._center_stage()
        self._animate()

    def _circle(self, presentation):
        accent = presentation["accent"]
        holder = FloatLayout(size_hint=(1, None), height=dp(88))
        surface = FloatLayout(size_hint=(None, None), size=(dp(88), dp(88)),
                              pos_hint={"center_x": 0.5, "y": 0})
        with surface.canvas:
            KvColor(accent[0], accent[1], accent[2], ICON_SURFACE_ALPHA / 255)
            surface._oval = Ellipse(pos=surface.pos, size=surface.size)
        surface.bind(pos=lambda w, _: setattr(w._oval, "pos", w.pos),
                     size=lambda w, _: setattr(w._oval, "size", w.size))
        if presentation["glyph"] == "unverified":
            mark = Label(text="?", font_size="40sp", bold=True,
                         color=accent, size_hint=(None, None),
                         size=surface.size)
            surface.add_widget(mark)
            mark.pos = surface.pos
            surface.bind(pos=lambda w, pos: setattr(mark, "pos", pos),
                         size=lambda w, size: setattr(mark, "size", size))
        else:
            surface.add_widget(Glyph(presentation["glyph"], accent,
                                     size_hint=(None, None),
                                     size=(dp(40), dp(40)),
                                     pos_hint={"center_x": 0.5, "center_y": 0.5}))
        holder.add_widget(surface)
        return self._fade_in(holder)

    def _details_card(self, bank_name, reference, date_time, upi_id, recipient):
        card = FloatLayout(size_hint=(1, None))
        with card.canvas.before:
            KvColor(rgba=theme.DARK_GRAY)
            card._bg = RoundedRectangle(pos=card.pos, size=card.size,
                                        radius=[dp(20)])
        card.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        column = BoxLayout(orientation="vertical", size_hint=(1, 1),
                           spacing=dp(10), padding=(dp(20), dp(18), dp(20), dp(18)))
        column.bind(minimum_height=lambda w, h: setattr(card, "height", h))
        for label_text, value_text in (
                (None, bank_name), ("Transaction ID", reference),
                ("Date", date_time),
                *((("UPI ID", upi_id),) if upi_id else ()),
                 *(( (recipient[0], recipient[1]),) if recipient else ())):
            if label_text is None:
                row = _left(value_text, 16, theme.TEXT_WHITE, bold=True)
                row.size_hint_y = None
                row.height = dp(22)
            else:
                row = BoxLayout(orientation="horizontal", size_hint=(1, None),
                                height=dp(22), spacing=dp(12))
                label = _left(label_text, 13, theme.TEXT_LIGHT_GRAY)
                label.size_hint_x = None
                label.width = dp(110)
                row.add_widget(label)
                value = _left(value_text, 14, theme.TEXT_WHITE)
                value.halign = "right"
                row.add_widget(value)
            column.add_widget(row)
        card.add_widget(column)
        column.pos = card.pos
        card.bind(pos=lambda w, pos: setattr(column, "pos", pos))
        return card

    def _done_button(self):
        holder = FloatLayout(size_hint=(1, None), height=dp(52))
        button = Button(text="Done", font_size="16sp", bold=True,
                        color=self._accent_theme.on_primary_dark,
                        size_hint=(1, 1),
                        background_normal="", background_down="",
                        background_color=(0, 0, 0, 0))
        with button.canvas.before:
            KvColor(rgba=self._accent_theme.primary_dark)
            button._bg = RoundedRectangle(pos=button.pos, size=button.size,
                                          radius=[dp(BUTTON_RADIUS_DP)])
        button.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                    size=lambda w, _: setattr(w._bg, "size", w.size),
                    on_release=lambda *_: self._on_done())
        holder.add_widget(button)
        button.pos = holder.pos
        holder.bind(pos=lambda w, pos: setattr(button, "pos", pos))
        return holder

    # -- entry animation --------------------------------------------------------

    def _fade_in(self, widget):
        widget.opacity = 0
        self._animated.append(widget)
        return widget

    def _animate(self):
        for index, widget in enumerate(self._animated):
            Animation.cancel_all(widget)
            widget.opacity = 0
            if self._animations_enabled:
                (Animation(opacity=1, duration=ENTRY_DURATION_MS / 1000,
                           t="out_cubic",
                           d=index * ENTRY_STAGGER_MS / 1000)).start(widget)
            else:
                widget.opacity = 1


def _spacer(height_dp):
    return BoxLayout(size_hint=(1, None), height=dp(height_dp))


def _left(text, size, color, bold=False):
    label = Label(text=text, font_size=f"{size}sp", color=color, bold=bold,
                  halign="left", valign="middle")
    label.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
    return label
