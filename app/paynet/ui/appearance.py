# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/AppearanceSetupActivity.kt and
# app/src/main/java/com/paynet/app/ui/home/HomeAppearancePreview.kt

"""Appearance introduction: choose Modern or Classic once, then the welcome
beat, then home.

DEVIATIONS (recorded in MIGRATION.md): the BackHandler becomes an injected
on_back callback (Kivy has no back stack here; the app shell wires the
Android back key in feature 17), TextAutoSize.StepBased becomes a fixed
44sp label with the same two-line copy, and the fade uses Kivy Animation
with the same timings (650ms in, 1600ms hold, 450ms out); the
reduced-animator path (snap + hold) is selected by passing
animations_enabled=False.
"""

from kivy.animation import Animation
from kivy.graphics import Color as KvColor, Ellipse, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import ButtonBehavior
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

from paynet import theme
from paynet import onboarding
from paynet.ui.home import Glyph, _gradient_texture
from paynet.ui.home_appearance import HomeAppearance
from paynet.ui.onboarding import OnboardingPage, _spacer

APPEARANCE_TITLE = "Make it yours."
APPEARANCE_SUBTITLE = "Choose your home screen.\nYou can change it in Settings."
APPEARANCE_MODERN = "Modern"
APPEARANCE_MODERN_DETAIL = "Cards and quick actions."
APPEARANCE_CLASSIC = "Classic"
APPEARANCE_CLASSIC_DETAIL = "Simple, focused controls."
APPEARANCE_WELCOME = "Hello, offline\npayments."

WELCOME_ENTER_MS = 650
WELCOME_HOLD_MS = 1600
WELCOME_EXIT_MS = 450
WELCOME_REDUCED_HOLD_MS = 1600

_PREVIEW_HISTORY = (0x12 / 255, 0x12 / 255, 0x13 / 255, 1)


class HomeAppearancePreview(FloatLayout):
    """HomeAppearancePreview.kt: an abstract, inert view of each arrangement
    (108x112 in the choice card). Black r14 canvas, gradient overview card,
    action squares and the history bar."""

    def __init__(self, appearance: HomeAppearance, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(108), dp(112)))
        super().__init__(**kwargs)
        self._appearance = appearance
        self.bind(pos=self._draw, size=self._draw)
        self._draw()

    def _draw(self, *_):
        self.canvas.clear()
        palette = theme.accent_theme_for(self._appearance.monochrome)
        control = palette.header_gradient_end
        ink = theme.HOME_INK if self._appearance.monochrome else (1, 1, 1, 1)
        x, y = self.pos
        w, h = self.size
        pad = dp(10)
        gap = dp(8)
        ix, iy = x + pad, y + pad
        iw, ih = w - pad * 2, h - pad * 2
        with self.canvas:
            KvColor(0, 0, 0, 1)
            RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(14)])

            def overview(ox, oy, ow, oh):
                KvColor(1, 1, 1, 1)
                card = RoundedRectangle(pos=(ox, oy), size=(ow, oh), radius=[dp(9)])
                card.texture = _gradient_texture(
                    palette.header_gradient_start, palette.header_gradient_end)

            def action(ax, ay, size, round_=False):
                KvColor(rgba=control)
                if round_:
                    Ellipse(pos=(ax, ay), size=(size, size))
                else:
                    RoundedRectangle(pos=(ax, ay), size=(size, size), radius=[dp(9)])

            if self._appearance.classic:
                # Overview card on top; centred QR (round) + person actions.
                action_h = dp(27)
                overview(ix, iy + action_h + gap, iw, ih - action_h - gap)
                row_w = dp(27) + dp(10) + dp(25)
                ax = ix + (iw - row_w) / 2
                action(ax, iy, dp(27), round_=True)
                action(ax + dp(27) + dp(10), iy + dp(1), dp(25))
            else:
                # Overview card left, arrow + QR actions right, history bar.
                history_h = dp(20)
                top_h = ih - history_h - gap
                action_w = dp(29)
                overview(ix, iy + history_h + gap, iw - action_w - dp(7), top_h)
                ax = ix + iw - action_w
                action(ax, iy + history_h + gap + top_h - action_w, action_w)
                action(ax, iy + history_h + gap + top_h - action_w * 2 - dp(6), action_w)
                KvColor(rgba=_PREVIEW_HISTORY)
                RoundedRectangle(pos=(ix, iy), size=(iw, history_h), radius=[dp(6)])


class _AppearanceChoice(ButtonBehavior, BoxLayout):
    """One clickable choice row: preview, label and description."""

    def __init__(self, label, description, appearance, on_click, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint", (1, None))
        kwargs.setdefault("height", dp(112) + dp(36))
        kwargs.setdefault("spacing", dp(20))
        kwargs.setdefault("padding", (dp(18), dp(18), dp(18), dp(18)))
        super().__init__(**kwargs)
        self._on_click = on_click
        with self.canvas.before:
            KvColor(rgba=theme.ONBOARDING_SURFACE)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(22)])
        self.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        self.add_widget(HomeAppearancePreview(appearance,
                                              pos_hint={"center_y": 0.5}))
        texts = BoxLayout(orientation="vertical", spacing=dp(6),
                          pos_hint={"center_y": 0.5})
        title = Label(text=label, font_size="18sp", bold=True,
                      color=theme.TEXT_WHITE, halign="left", valign="bottom",
                      size_hint=(1, None), height=dp(26))
        title.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
        detail = Label(text=description, font_size="14sp",
                       color=theme.ONBOARDING_SECONDARY, halign="left",
                       valign="top", size_hint=(1, None), height=dp(22))
        detail.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
        texts.add_widget(title)
        texts.add_widget(detail)
        self.add_widget(texts)

    def on_release(self):
        self._on_click()


class AppearanceScreen(FloatLayout):
    """AppearanceSetupActivity: choices -> welcome -> home, once.

    on_open_home: called after the welcome beat completes (guarded once);
    on_review_setup: BackHandler's setup branch (review mode)."""

    def __init__(self, prefs, on_open_home, on_review_setup=None,
                 animations_enabled=True, **kwargs):
        kwargs.setdefault("size_hint", (1, 1))
        super().__init__(**kwargs)
        self._prefs = prefs
        self._on_open_home = on_open_home
        self._on_review_setup = on_review_setup
        self._animations_enabled = animations_enabled
        self._has_navigated = False
        self._welcome = None
        self._choices = None
        # Preferences are the source of truth across recreation, including a
        # process loss after selection but before a saved-state snapshot.
        if onboarding.has_chosen_appearance(prefs):
            self._show_welcome()
        else:
            self._show_choices()

    def _show_choices(self):
        if self._welcome is not None:
            self.remove_widget(self._welcome)
            self._welcome = None
        page = OnboardingPage()
        heading = BoxLayout(orientation="vertical", size_hint=(1, None), spacing=0)
        icon = FloatLayout(size_hint=(1, None), height=dp(48))
        icon.add_widget(Glyph("dashboard", theme.VIOLET_ACCENT_THEME.primary,
                              size_hint=(None, None), size=(dp(48), dp(48)),
                              pos_hint={"center_x": 0.5, "y": 0}))
        heading.add_widget(icon)
        heading.add_widget(_spacer(16))
        title = Label(text=APPEARANCE_TITLE, font_size="31sp", bold=True,
                      color=theme.TEXT_WHITE, size_hint=(1, None), halign="center")
        title.bind(texture_size=lambda w, s: setattr(w, "height", s[1]))
        heading.add_widget(title)
        heading.add_widget(_spacer(8))
        subtitle = Label(text=APPEARANCE_SUBTITLE, font_size="15sp",
                         color=theme.ONBOARDING_SECONDARY, size_hint=(1, None),
                         halign="center")
        subtitle.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)),
                      texture_size=lambda w, s: setattr(w, "height", s[1]))
        heading.add_widget(subtitle)
        heading.bind(minimum_height=heading.setter("height"))
        page.add_content(heading)
        page.add_content(_spacer(28))
        page.add_content(_AppearanceChoice(
            APPEARANCE_MODERN, APPEARANCE_MODERN_DETAIL,
            HomeAppearance(classic=False),
            lambda: self._choose(False)))
        page.add_content(_spacer(12))
        page.add_content(_AppearanceChoice(
            APPEARANCE_CLASSIC, APPEARANCE_CLASSIC_DETAIL,
            HomeAppearance(classic=True),
            lambda: self._choose(True)))
        self._choices = page
        self.add_widget(page)

    def _choose(self, classic):
        onboarding.choose_appearance(self._prefs, classic)
        if self._choices is not None:
            self.remove_widget(self._choices)
            self._choices = None
        self._show_welcome()

    def _show_welcome(self):
        welcome = FloatLayout(size_hint=(1, 1))
        with welcome.canvas.before:
            KvColor(0, 0, 0, 1)
            welcome._bg = RoundedRectangle(pos=welcome.pos, size=welcome.size,
                                           radius=[0])
        welcome.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                     size=lambda w, _: setattr(w._bg, "size", w.size))
        copy = Label(text=APPEARANCE_WELCOME, font_size="44sp", bold=True,
                     color=theme.WELCOME_TEXT, halign="center", valign="middle",
                     size_hint=(None, None))
        copy.line_height = 52 / 44
        copy.bind(size=lambda w, _: setattr(w, "text_size", w.size))
        welcome.add_widget(copy)
        welcome.bind(size=lambda w, s: setattr(copy, "size",
                                               (s[0] - dp(64), s[1] - dp(64))),
                     pos=lambda w, p: setattr(copy, "center", w.center))
        copy.opacity = 0
        self._welcome = welcome
        self.add_widget(welcome)

        if self._animations_enabled:
            anim = (Animation(opacity=1, duration=WELCOME_ENTER_MS / 1000,
                              t="out_cubic")
                    + Animation(duration=WELCOME_HOLD_MS / 1000)
                    + Animation(opacity=0, duration=WELCOME_EXIT_MS / 1000,
                                t="in_cubic"))
            anim.bind(on_complete=lambda *_: self._complete_introduction())
            anim.start(copy)
        else:
            copy.opacity = 1
            Animation(duration=WELCOME_REDUCED_HOLD_MS / 1000).start(copy)
            from kivy.clock import Clock
            Clock.schedule_once(lambda *_: self._complete_introduction(),
                                WELCOME_REDUCED_HOLD_MS / 1000)

    def _complete_introduction(self):
        if self._has_navigated:
            return
        self._has_navigated = True
        onboarding.complete_welcome(self._prefs)
        self._on_open_home()

    def on_back(self):
        """BackHandler: reviewing from the welcome beat re-opens the choices;
        from the choices it returns to setup in review mode."""
        if self._welcome is not None:
            onboarding.review_appearance(self._prefs)
            self._show_choices()
        elif self._on_review_setup is not None:
            self._on_review_setup()
