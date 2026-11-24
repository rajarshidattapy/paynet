# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/services/CallOverlayView.kt and
# CallOverlayMessageMotion.kt

"""The in-call overlay card: display-only construction and display pacing.
Neither owns payment or call state; the bar estimates call guidance and only
the session supplies payment outcomes, so pacing NEVER reaches 100%.

DEVIATIONS (recorded in MIGRATION.md): WindowManager flags/overlay window
type are platform concerns; animation frames are computed from an injectable
monotonic clock instead of ValueAnimator so the pacing rules are testable;
the Kivy widget drives itself with Clock when attached.
"""

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color as KvColor, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

from paynet import theme
from paynet.ui.home import Glyph
from paynet.utils.currency import inr
from paynet.utils.phone import format_phone_for_display

VISIBLE_PHONE_DIGITS = 4
PROGRESS_MAX = 1000
PROGRESS_CEILING = 900
UNITS_PER_PERCENT = 10
CONNECTING_PROGRESS = 100
IN_CALL_PROGRESS = 200
MILESTONE_MS = 1000
CALL_PACING_MS = 31000
PIN_GUIDANCE_DELAY_MS = 2500
AUTH_GUIDANCE_DELAY_AFTER_PIN_MS = 16500
ENTRANCE_MS = 180
SHIFT_DP = 6
FADE_OUT_MS = 100
REFLOW_MS = 300

PROCESSING_PAYMENT = "Processing Payment"
CONNECTING = "Connecting to the UPI service…"
SENDING_REQUEST = "Sending your payment request…"
PIN_NOTICE = ("PayNet never asks for your UPI PIN. Your bank will call you — "
              "enter your PIN on that call.")
AUTH_NOTICE = ("On the bank callback for this payment, check the amount and "
               "recipient. Press 1 to confirm, then enter your UPI PIN when "
               "prompted.")
SECURE_TRANSFER = "Secure Transfer"
AMOUNT_LABEL = "Amount"
TO_LABEL = "To"
AUDIO_MUTED = "Call volume lowered"
TERMINATE = "Cancel payment"

# The overlay's own light "frosted" mini palette (colors.xml).
CARD_BG = (1, 1, 1, 0.95)
GREEN = (0x4C / 255, 0xAF / 255, 0x50 / 255, 1)
TEXT_DARK = (0x17 / 255, 0x16 / 255, 0x1F / 255, 1)
TEXT_PRIMARY = (0x2C / 255, 0x2C / 255, 0x2C / 255, 1)
TEXT_SECONDARY = (0x75 / 255, 0x75 / 255, 0x75 / 255, 1)
ICON_GRAY = (0x42 / 255, 0x42 / 255, 0x42 / 255, 1)
DIVIDER = (0xE0 / 255, 0xE0 / 255, 0xE0 / 255, 1)
ALERT_RED = (1, 0x6B / 255, 0x6B / 255, 1)
TERMINATE_RED = (1, 0x44 / 255, 0x44 / 255, 1)


def progress_percent(progress: int) -> int:
    return progress // UNITS_PER_PERCENT


def clamp_progress(value: int) -> int:
    """Call guidance only: the estimate never reaches 100%."""
    return max(0, min(value, PROGRESS_CEILING))


class CallOverlayProgress:
    """Owns display pacing only. progress_at(now) is the frame callback's
    pure core: CONNECTING eases to 10% over 1s; IN_CALL holds the 20%
    milestone at 1s and crawls to the 90% ceiling over 31s; STOPPED freezes
    and cannot restart."""

    CONNECTING = "CONNECTING"
    IN_CALL = "IN_CALL"
    STOPPED = "STOPPED"

    def __init__(self, view, animations_enabled=lambda: True, now=None):
        self._view = view
        self._animations_enabled = animations_enabled
        self._now = now or (lambda: Clock.get_boottime() * 1000)
        self.phase = None
        self._started_at = 0.0
        self._start_value = 0
        self._milestone = 0

    def show_connecting(self):
        if self.phase is not None:
            return
        self.phase = self.CONNECTING
        self._begin(milestone=CONNECTING_PROGRESS, duration_ms=MILESTONE_MS)

    def show_in_call(self):
        if self.phase in (self.IN_CALL, self.STOPPED):
            return
        self.phase = self.IN_CALL
        current = self._view.progress
        self._begin(milestone=max(current, IN_CALL_PROGRESS),
                    duration_ms=CALL_PACING_MS)

    def _begin(self, milestone, duration_ms):
        self._start_value = self._view.progress
        self._milestone = milestone
        self._duration_ms = duration_ms
        self._started_at = self._now()
        if not self._animations_enabled():
            # Reduced motion retains a clear phase milestone without
            # continuous movement.
            self._view.show_progress(milestone)

    def progress_at(self, now_ms) -> int:
        """The animated value at a moment, per the Kotlin keyframes."""
        if not self._animations_enabled() or self.phase in (None, self.STOPPED):
            return self._view.progress
        fraction = max(0.0, min(1.0, (now_ms - self._started_at) / self._duration_ms))
        if self.phase == self.CONNECTING:
            value = self._start_value + (self._milestone - self._start_value) * fraction
        else:  # IN_CALL: reach the milestone at MILESTONE_MS of the pacing
            keyframe = MILESTONE_MS / CALL_PACING_MS
            if fraction <= keyframe:
                inner = fraction / keyframe if keyframe else 1.0
                value = self._start_value + (self._milestone - self._start_value) * inner
            else:
                inner = (fraction - keyframe) / (1 - keyframe)
                value = self._milestone + (PROGRESS_CEILING - self._milestone) * inner
        return int(value)

    def tick(self, now_ms=None):
        if self.phase in (None, self.STOPPED):
            return
        self._view.show_progress(self.progress_at(now_ms if now_ms is not None
                                                  else self._now()))

    def stop(self):
        self.phase = self.STOPPED


class CallOverlayMessageMotion:
    """Coordinates guidance copy changes: with animations, fade out over
    100ms, swap the text, settle back over 300ms; otherwise swap at once."""

    def __init__(self, message_label, animations_enabled=lambda: True):
        self._message = message_label
        self._animations_enabled = animations_enabled
        self._stopped = False

    def show(self, text):
        if self._stopped:
            return
        Animation.cancel_all(self._message)
        self._message.opacity = 1
        if not self._animations_enabled():
            self._message.text = text
            return
        (Animation(opacity=0, duration=FADE_OUT_MS / 1000)
         + Animation(_on_complete=lambda *_: setattr(self._message, "text", text),
                     duration=0)
         + Animation(opacity=1, duration=REFLOW_MS / 1000)).start(self._message)

    def stop(self):
        self._stopped = True
        Animation.cancel_all(self._message)
        self._message.opacity = 1


class CallOverlayView(FloatLayout):
    """call_overlay_paynet.xml as a widget: the frosted card (logo, secure
    badge, status, progress bar + percent, step text, amount/recipient
    details, volume pill, terminate button) centered on a transparent field.
    Display-only: on_terminate is the service's hook."""

    def __init__(self, on_terminate=None, **kwargs):
        kwargs.setdefault("size_hint", (1, 1))
        super().__init__(**kwargs)
        self._on_terminate = on_terminate or (lambda: None)
        self.progress = 0

        card = FloatLayout(size_hint=(None, None), width=dp(364),
                           pos_hint={"center_x": 0.5, "center_y": 0.5})
        with card.canvas.before:
            KvColor(rgba=CARD_BG)
            card._bg = RoundedRectangle(pos=card.pos, size=card.size,
                                        radius=[dp(28)])
        card.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        self._card = card

        column = BoxLayout(orientation="vertical", size_hint=(None, None),
                           width=dp(364), spacing=0,
                           padding=(dp(32), dp(28), dp(32), dp(20)))
        column.bind(minimum_height=column.setter("height"))
        card.bind(height=lambda w, h: setattr(card, "height", h),
                  pos=lambda w, p: setattr(column, "pos", p),
                  width=lambda w, wd: setattr(column, "width", wd))
        column.bind(height=lambda w, h: setattr(card, "height", h))
        card.add_widget(column)
        self._column = column

        logo = Label(text="PayNet", font_size="20sp", color=TEXT_PRIMARY,
                     size_hint=(1, None), height=dp(26), halign="center")
        logo.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
        column.add_widget(logo)
        column.add_widget(_gap(12))

        badge = BoxLayout(orientation="horizontal", size_hint=(None, None),
                          height=dp(28), spacing=dp(6),
                          padding=(dp(12), dp(6), dp(12), dp(6)),
                          pos_hint={"center_x": 0.5})
        badge.bind(minimum_width=badge.setter("width"))
        with badge.canvas.before:
            KvColor(GREEN[0], GREEN[1], GREEN[2], 0.12)
            badge._bg = RoundedRectangle(pos=badge.pos, size=badge.size,
                                         radius=[dp(14)])
        badge.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                   size=lambda w, _: setattr(w._bg, "size", w.size))
        badge.add_widget(Glyph("check", GREEN, size_hint=(None, None),
                               size=(dp(14), dp(14)), pos_hint={"center_y": 0.5}))
        badge.add_widget(Label(text=SECURE_TRANSFER, font_size="13sp",
                               color=GREEN, size_hint=(None, 1)))
        badge.children[0].bind(
            texture_size=lambda w, s: setattr(w, "width", s[0]))
        column.add_widget(_center(badge, dp(28)))
        column.add_widget(_gap(20))

        self.status_text = Label(text=PROCESSING_PAYMENT, font_size="24sp",
                                 bold=True, color=TEXT_DARK,
                                 size_hint=(1, None), halign="center")
        self.status_text.bind(
            width=lambda w, _: setattr(w, "text_size", (w.width, None)),
            texture_size=lambda w, s: setattr(w, "height", s[1]))
        column.add_widget(self.status_text)
        column.add_widget(_gap(28))

        progress_row = BoxLayout(orientation="horizontal", size_hint=(1, None),
                                 height=dp(16), spacing=dp(12))
        self._track = FloatLayout(size_hint=(1, 1))
        with self._track.canvas.before:
            KvColor(1, 1, 1, 0.6)
            self._track._bg = RoundedRectangle(pos=self._track.pos,
                                               size=self._track.size,
                                               radius=[dp(8)])
        with self._track.canvas:
            KvColor(rgba=GREEN)
            self._fill = RoundedRectangle(pos=self._track.pos,
                                          size=(0, self._track.height),
                                          radius=[dp(8)])
        self._track.bind(pos=self._layout_progress, size=self._layout_progress)
        progress_row.add_widget(self._track)
        self.percent_text = Label(text="0%", font_size="12sp", bold=True,
                                  color=GREEN, size_hint=(None, 1),
                                  width=dp(34), halign="right")
        self.percent_text.bind(
            size=lambda w, _: setattr(w, "text_size", w.size))
        progress_row.add_widget(self.percent_text)
        column.add_widget(progress_row)
        column.add_widget(_gap(16))

        self.step_text = Label(text=CONNECTING, font_size="16sp", bold=True,
                               color=ICON_GRAY, size_hint=(1, None),
                               halign="center")
        self.step_text.bind(
            width=lambda w, _: setattr(w, "text_size", (w.width, None)),
            texture_size=lambda w, s: setattr(w, "height", s[1]))
        column.add_widget(self.step_text)
        column.add_widget(_gap(24))

        details = BoxLayout(orientation="horizontal", size_hint=(1, None),
                            height=dp(76), padding=(dp(20), dp(20), dp(20), dp(20)))
        with details.canvas.before:
            KvColor(1, 1, 1, 1)
            details._bg = RoundedRectangle(pos=details.pos, size=details.size,
                                           radius=[dp(20)])
        details.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                     size=lambda w, _: setattr(w._bg, "size", w.size))
        self.amount_text, amount_cell = self._detail_cell("₹0", AMOUNT_LABEL)
        details.add_widget(amount_cell)
        divider = FloatLayout(size_hint=(None, 1), width=dp(1))
        with divider.canvas:
            KvColor(rgba=DIVIDER)
            divider._line = RoundedRectangle(pos=divider.pos,
                                             size=(dp(1), dp(40)), radius=[0])
        divider.bind(pos=lambda w, _: setattr(
            w._line, "pos", (w.x, w.center_y - dp(20))))
        details.add_widget(divider)
        self.recipient_text, recipient_cell = self._detail_cell("••••••0000", TO_LABEL)
        details.add_widget(recipient_cell)
        column.add_widget(details)

        self._muted_holder = BoxLayout(size_hint=(1, None), height=0, opacity=0)
        pill = BoxLayout(orientation="horizontal", size_hint=(None, None),
                         height=dp(34), spacing=dp(8),
                         padding=(dp(16), dp(8), dp(16), dp(8)),
                         pos_hint={"center_x": 0.5})
        pill.bind(minimum_width=pill.setter("width"))
        with pill.canvas.before:
            KvColor(ALERT_RED[0], ALERT_RED[1], ALERT_RED[2], 0.1)
            pill._bg = RoundedRectangle(pos=pill.pos, size=pill.size,
                                        radius=[dp(17)])
        pill.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        pill.add_widget(Label(text=AUDIO_MUTED, font_size="14sp",
                              color=ALERT_RED, size_hint=(None, 1)))
        pill.children[0].bind(texture_size=lambda w, s: setattr(w, "width", s[0]))
        self._muted_holder.add_widget(_center(pill, dp(34)))
        column.add_widget(_gap(20))
        column.add_widget(self._muted_holder)

        terminate = Button(text=TERMINATE, font_size="12sp", bold=True,
                           color=(1, 1, 1, 1), size_hint=(None, None),
                           height=dp(48), background_normal="",
                           background_down="", background_color=(0, 0, 0, 0))
        terminate.bind(texture_size=lambda w, s: setattr(w, "width", s[0] + dp(32)),
                       on_release=lambda *_: self._on_terminate())
        with terminate.canvas.before:
            KvColor(rgba=TERMINATE_RED)
            terminate._bg = RoundedRectangle(pos=terminate.pos,
                                             size=terminate.size,
                                             radius=[dp(28)])
        terminate.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                       size=lambda w, _: setattr(w._bg, "size", w.size))
        column.add_widget(_center(terminate, dp(48)))

        self.add_widget(card)

    def _detail_cell(self, value, caption):
        cell = BoxLayout(orientation="vertical", size_hint=(1, 1), spacing=dp(4))
        value_label = Label(text=value, font_size="20sp", bold=True,
                            color=TEXT_DARK, size_hint=(1, 1), halign="center")
        value_label.bind(size=lambda w, _: setattr(w, "text_size", w.size))
        caption_label = Label(text=caption, font_size="13sp",
                              color=TEXT_SECONDARY, size_hint=(1, None),
                              height=dp(18), halign="center")
        caption_label.bind(size=lambda w, _: setattr(w, "text_size", w.size))
        cell.add_widget(value_label)
        cell.add_widget(caption_label)
        return value_label, cell

    # -- CallOverlayView statics -------------------------------------------------

    def bind_details(self, phone_number, amount):
        """CallOverlayView.bind: a reused view resets to the connecting look."""
        self.amount_text.text = f"₹{inr(amount)}"
        self.recipient_text.text = format_phone_for_display(phone_number,
                                                            VISIBLE_PHONE_DIGITS)
        self.show_progress(0)
        self.status_text.text = PROCESSING_PAYMENT
        self.step_text.text = CONNECTING

    def show_progress(self, value):
        self.progress = clamp_progress(value)
        label = f"{progress_percent(self.progress)}%"
        if self.percent_text.text != label:
            self.percent_text.text = label
        self._layout_progress()

    def _layout_progress(self, *_):
        track = self._track
        self._track._bg.pos = track.pos
        self._track._bg.size = track.size
        fraction = self.progress / PROGRESS_MAX
        self._fill.pos = track.pos
        self._fill.size = (track.width * fraction, track.height)

    def show_muted_indicator(self):
        """Only after the volume change actually worked."""
        self._muted_holder.height = dp(34)
        self._muted_holder.opacity = 1

    def update_status(self, status, step):
        self.status_text.text = status
        self.step_text.text = step

    def schedule_bank_guidance(self, motion, scheduler=None):
        """PIN guidance at 2.5s, authentication guidance 16.5s later."""
        schedule = scheduler or Clock.schedule_once
        schedule(lambda *_: motion.show(PIN_NOTICE),
                 PIN_GUIDANCE_DELAY_MS / 1000)
        schedule(lambda *_: motion.show(AUTH_NOTICE),
                 (PIN_GUIDANCE_DELAY_MS + AUTH_GUIDANCE_DELAY_AFTER_PIN_MS) / 1000)


def _gap(height_dp):
    return BoxLayout(size_hint=(1, None), height=dp(height_dp))


def _center(widget, height_dp):
    holder = FloatLayout(size_hint=(1, None), height=dp(height_dp))
    widget.pos_hint = {"center_x": 0.5, "center_y": 0.5}
    holder.add_widget(widget)
    return holder
