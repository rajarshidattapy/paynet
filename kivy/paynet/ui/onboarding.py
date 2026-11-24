# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/OnboardingPage.kt and
# app/src/main/java/com/paynet/app/ui/dialogs/OnboardingDialog(+Copy).kt

"""Shared onboarding page scaffold and the onboarding dialog.

DEVIATIONS (recorded in MIGRATION.md): the vertical-scroll Column becomes a
plain anchored Column (the pages fit the viewport; scrolling was a
small-screen safeguard), the CircularProgressIndicator in
OnboardingDialogProgress is an animated ellipsis label, and the Dialog
window becomes a centred overlay layer on the app root.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from kivy.animation import Animation
from kivy.graphics import Color as KvColor, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from paynet import theme
from paynet.ui.home import Glyph


@dataclass(frozen=True)
class OnboardingDialogCopy:
    title: str
    message: Optional[str] = None


def _left_label(text, size, color, bold=False):
    label = Label(text=text, font_size=f"{size}sp", color=color,
                  halign="left", valign="top", bold=bold)
    label.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
    return label


class OnboardingPage(FloatLayout):
    """OnboardingPage.kt: black viewport, header at 18.75% of height, content
    column capped at 420dp with 24dp side padding, horizontally centred."""

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint", (1, 1))
        super().__init__(**kwargs)
        with self.canvas.before:
            KvColor(0, 0, 0, 1)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[0])
        self.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        self._scroll = ScrollView(size_hint=(1, 1))
        self._column = BoxLayout(orientation="vertical",
                                 size_hint=(None, None), spacing=0)
        self._column.bind(minimum_height=self._column.setter("height"))
        self._stack = BoxLayout(orientation="vertical", size_hint=(1, None),
                                spacing=0)
        self._stack.bind(minimum_height=self._stack.setter("height"))
        self._column.add_widget(self._stack)
        self._scroll.add_widget(self._column)
        self.add_widget(self._scroll)
        self.bind(pos=self._relayout, size=self._relayout)
        self._relayout()

    def _relayout(self, *_):
        w, h = self.size
        content_w = min(w - dp(48), dp(420))
        # The ScrollView owns the column's position (scroll_y); center the
        # content with symmetric side padding instead of setting pos.
        side = (w - content_w) / 2
        self._column.width = w
        header_offset = h * 0.1875
        self._column.padding = (side, header_offset, side, dp(24))

    def add_content(self, widget):
        self._stack.add_widget(widget)


class OnboardingDialog(FloatLayout):
    """OnboardingDialog.kt: centred card (max 400dp, r24, surface) with a
    title row + close button, optional message, content and actions. Not
    dismissible by outside touch, like dismissOnClickOutside = false."""

    def __init__(self, copy: OnboardingDialogCopy, on_dismiss: Callable[[], None],
                 **kwargs):
        kwargs.setdefault("size_hint", (1, 1))
        super().__init__(**kwargs)
        self._on_dismiss = on_dismiss
        with self.canvas.before:
            KvColor(0, 0, 0, 0.6)
            self._scrim = RoundedRectangle(pos=self.pos, size=self.size, radius=[0])
        self.bind(pos=lambda w, _: setattr(w._scrim, "pos", w.pos),
                  size=lambda w, _: setattr(w._scrim, "size", w.size))

        self._card = FloatLayout(size_hint=(None, None))
        with self._card.canvas.before:
            KvColor(rgba=theme.ONBOARDING_SURFACE)
            self._card_bg = RoundedRectangle(pos=self._card.pos,
                                             size=self._card.size,
                                             radius=[dp(24)])
        card_bg = self._card_bg
        self._card.bind(pos=lambda w, _: setattr(card_bg, "pos", w.pos),
                        size=lambda w, _: setattr(card_bg, "size", w.size))
        self._body = BoxLayout(orientation="vertical", spacing=0,
                               size_hint=(None, None),
                               padding=(dp(24), dp(24), dp(24), dp(24)))
        self._body.bind(minimum_height=self._body.setter("height"))
        self._body.bind(height=lambda w, h: setattr(self._card, "height", h),
                        width=lambda w, wd: setattr(self._card, "width", wd))
        self._card.add_widget(self._body)

        heading = BoxLayout(orientation="horizontal", size_hint=(1, None),
                            height=dp(56), spacing=dp(8))
        title = _left_label(copy.title, 24, theme.TEXT_WHITE, bold=True)
        title.line_height = 29 / 24
        heading.add_widget(title)
        close = Button(size_hint=(None, None), size=(dp(48), dp(48)),
                       background_normal="",
                       background_color=(0, 0, 0, 0))
        glyph = Glyph("close", theme.TEXT_LIGHT_GRAY,
                      size_hint=(None, None), size=(dp(22), dp(22)))
        close.add_widget(glyph)
        def _place_glyph(w, *_):
            glyph.center = (w.x + w.width / 2, w.y + w.height / 2)
        close.bind(pos=_place_glyph, size=_place_glyph)
        _place_glyph(close)
        close.bind(on_release=lambda *_: self._on_dismiss())
        heading.add_widget(close)
        self._body.add_widget(heading)

        if copy.message:
            self._body.add_widget(_spacer(8))
            message = _left_label(copy.message, 16, theme.TEXT_LIGHT_GRAY)
            message.line_height = 23 / 16
            message.size_hint_y = None
            message.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1]))
            self._body.add_widget(message)

        self._content = BoxLayout(orientation="vertical", size_hint=(1, None),
                                  spacing=0, height=0)
        self._content.bind(minimum_height=self._content.setter("height"))
        self._body.add_widget(self._content)

        self._body.add_widget(_spacer(24))
        self._actions = BoxLayout(orientation="vertical", size_hint=(1, None),
                                  spacing=dp(4))
        self._actions.bind(minimum_height=self._actions.setter("height"))
        self._body.add_widget(self._actions)

        self.add_widget(self._card)
        self.bind(pos=self._relayout, size=self._relayout)
        self._relayout()

    def _relayout(self, *_):
        self._body.width = min(self.width - dp(48), dp(400))
        self._card.center = (self.center_x, self.center_y)
        self._body.pos = self._card.pos

    def add_content(self, widget):
        self._content.add_widget(widget)

    def add_action(self, widget):
        self._actions.add_widget(widget)


def _spacer(height_dp):
    return BoxLayout(size_hint=(1, None), height=dp(height_dp))


class OnboardingDialogAction(Button):
    """OnboardingDialogAction: primary = filled r14 primaryDark button;
    secondary = accent-coloured text button. Min height 48dp."""

    def __init__(self, text, on_release, secondary=False, enabled=True,
                 accent_theme=None, **kwargs):
        accent_theme = accent_theme or theme.VIOLET_ACCENT_THEME
        kwargs.setdefault("size_hint", (1, None))
        kwargs.setdefault("height", dp(48))
        super().__init__(text=text, font_size="16sp",
                         background_normal="",
                         disabled=not enabled, **kwargs)
        self._on_release_cb = on_release
        if secondary:
            self.background_color = (0, 0, 0, 0)
            self.color = accent_theme.accent
        else:
            self.background_color = accent_theme.primary_dark
            self.color = accent_theme.on_primary_dark
            self.bold = True
        self.bind(on_release=lambda *_: self._on_release_cb())


class OnboardingDialogProgress(BoxLayout):
    """OnboardingDialogProgress: spinner + message. DEVIATION: the
    CircularProgressIndicator is an animated ellipsis label."""

    def __init__(self, message, accent_theme=None, **kwargs):
        accent_theme = accent_theme or theme.VIOLET_ACCENT_THEME
        kwargs.setdefault("size_hint", (1, None))
        kwargs.setdefault("height", dp(40))
        kwargs.setdefault("spacing", dp(12))
        super().__init__(**kwargs)
        self.padding = (0, dp(20), 0, 0)
        self._spinner = Label(text="...", font_size="18sp",
                              color=accent_theme.accent,
                              size_hint=(None, 1), width=dp(20))
        self._label = _left_label(message, 14, theme.TEXT_LIGHT_GRAY)
        self._label.line_height = 20 / 14
        self.add_widget(self._spinner)
        self.add_widget(self._label)
        self._anim = Animation(opacity=0.25, duration=0.5) + Animation(opacity=1, duration=0.5)
        self._anim.repeat = True
        self._anim.start(self._spinner)


def onboarding_confirmation_actions(on_configured, on_not_configured):
    """OnboardingConfirmationActions: primary "Yes, it's set up" + secondary
    "Not yet"."""
    return [
        OnboardingDialogAction("Yes, it's set up", on_configured),
        OnboardingDialogAction("Not yet", on_not_configured, secondary=True),
    ]
