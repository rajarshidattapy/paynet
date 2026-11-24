# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/SetupActivity.kt

"""Setup screen: bank + calling-SIM selection, disclaimer consent and the
settle-then-advance completion flow.

DEVIATIONS (recorded in MIGRATION.md): ExposedDropdownMenuBox becomes a Kivy
Dropdown anchored to the row, the M3 Checkbox is a canvas-drawn box with the
check glyph, the page-transition animations of setupTransitionOptions are
dropped (ScreenManager default), and navigation to TestConfigurationActivity
is an injected callback (the destination screen is feature 16).
"""

from kivy.clock import Clock
from kivy.graphics import Color as KvColor, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button, ButtonBehavior
from kivy.uix.dropdown import DropDown
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

from paynet import theme
from paynet.setup import (SETUP_SETTLE_MS, SetupAdvanceState, SetupData,
                          SetupHelper, setup_selection_complete)
from paynet.ui.home import Glyph
from paynet.ui.onboarding import OnboardingPage, _left_label, _spacer

SETUP_TITLE = "Set up"
SETUP_SUBTITLE = "Choose the bank and SIM you use for UPI."
SETUP_BANK_LABEL = "Bank"
SETUP_BANK_PLACEHOLDER = "Choose your bank"
SETUP_SIM_LABEL = "Primary SIM"
SETUP_SIM_PLACEHOLDER = "Select your primary SIM"
SETUP_ACCEPT = "I have read and understood the disclaimer."
SETUP_READ = "Read disclaimer"
SETUP_HIDE = "Hide disclaimer"
DISCLAIMER_TEXT = (
    "PayNet is a free, open-source app. It is not a bank, wallet, or payment "
    "processor, and never holds your money.\n\n"
    "PayNet opens the *99# or UPI 123Pay call flow. You authorise payments "
    "directly with your bank. PayNet is not affiliated with NPCI or any bank.\n\n"
    "Your UPI PIN is entered only in the bank dialer or IVR flow. PayNet "
    "processes incoming bank SMS only during an active payment attempt. It "
    "never reads your inbox or uses accessibility services.\n\n"
    "Payment records stay on your device. Payment results are detected from "
    "matching bank confirmation messages. Missing messages do not prove that "
    "a payment failed. Check with your bank or recipient before retrying.\n\n"
    "By continuing, you confirm that you have read and understood this.")


class _CheckBox(ButtonBehavior, FloatLayout):
    """M3 Checkbox stand-in: 24dp rounded outline, accent fill + check when
    checked. clearAndSetSemantics: the row handles the toggle."""

    def __init__(self, checked=False, accent=None, on_change=None, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(24), dp(24)))
        super().__init__(**kwargs)
        self.checked = checked
        self._accent = accent or theme.VIOLET_ACCENT_THEME
        self._on_change = on_change
        with self.canvas:
            self._outline_color = KvColor(rgba=theme.ONBOARDING_OUTLINE)
            self._outline = Line(rounded_rectangle=(
                self.x, self.y, self.width, self.height, dp(4)), width=dp(2))
            self._fill_color = KvColor(rgba=(0, 0, 0, 0))
            self._fill = RoundedRectangle(pos=(self.x + dp(2), self.y + dp(2)),
                                          size=(self.width - dp(4), self.height - dp(4)),
                                          radius=[dp(3)])
        self._check = Glyph("check", theme.TEXT_WHITE,
                            size_hint=(None, None), size=(dp(16), dp(16)))
        self._check.opacity = 0
        self.add_widget(self._check)
        self.bind(pos=self._relayout, size=self._relayout)
        self._relayout()

    def _relayout(self, *_):
        self._outline.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(4))
        self._fill.pos = (self.x + dp(2), self.y + dp(2))
        self._fill.size = (self.width - dp(4), self.height - dp(4))
        self._check.center = self.center
        self._sync()

    def _sync(self):
        on = bool(self.checked)
        self._fill_color.rgba = self._accent.primary if on else (0, 0, 0, 0)
        self._outline_color.rgba = ((0, 0, 0, 0) if on else theme.ONBOARDING_OUTLINE)
        self._check.opacity = 1 if on else 0

    def set_checked(self, value):
        self.checked = value
        self._sync()

    def on_release(self):
        if self._on_change is not None:
            self._on_change(not self.checked)


class _SelectionRow(ButtonBehavior, BoxLayout):
    """SetupSelectionRow: leading accent icon, label + current value, and a
    trailing chevron; tapping opens the option menu."""

    def __init__(self, icon_kind, label, options, selected, on_selected,
                 on_editing, accent=None, placeholder="", **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint", (1, None))
        kwargs.setdefault("height", dp(76))
        kwargs.setdefault("spacing", dp(12))
        kwargs.setdefault("padding", (dp(18), dp(14), dp(18), dp(14)))
        super().__init__(**kwargs)
        self._accent = accent or theme.VIOLET_ACCENT_THEME
        self._placeholder = placeholder
        self._options = options
        self._selected = selected
        self._on_selected = on_selected
        self._on_editing = on_editing

        icon_holder = FloatLayout(size_hint=(None, None), size=(dp(22), dp(22)),
                                  pos_hint={"center_y": 0.5})
        icon_holder.add_widget(Glyph(icon_kind, self._accent.primary,
                                     size_hint=(1, 1), pos_hint={"x": 0, "y": 0}))
        self.add_widget(icon_holder)

        texts = BoxLayout(orientation="vertical", size_hint=(1, 1), spacing=dp(4))
        self._label = _left_label(label, 17, theme.TEXT_WHITE)
        self._label.bold = True
        self._value = _left_label(self._display_value(), 13,
                                  theme.ONBOARDING_SECONDARY)
        self._value.line_height = 18 / 13
        texts.add_widget(self._label)
        texts.add_widget(self._value)
        self.add_widget(texts)

        chevron_holder = FloatLayout(size_hint=(None, None), size=(dp(20), dp(20)),
                                     pos_hint={"center_y": 0.5})
        self._chevron = Glyph("chevron", theme.ONBOARDING_SECONDARY,
                              size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
        chevron_holder.add_widget(self._chevron)
        self.add_widget(chevron_holder)

        self._dropdown = DropDown(auto_width=False, width=dp(280))
        for value, title in options:
            item = Button(text=title, font_size="16sp",
                          size_hint_y=None, height=dp(48),
                          background_normal="", background_down="",
                          background_color=theme.ONBOARDING_SURFACE,
                          color=theme.TEXT_WHITE, halign="left")
            item.bind(on_release=lambda btn, v=value: self._pick(v))
            self._dropdown.add_widget(item)
        self._dropdown.bind(on_dismiss=self._dismissed)

    def _display_value(self):
        for value, title in self._options:
            if value == self._selected:
                return title
        return self._placeholder

    def set_placeholder(self, placeholder):
        self._placeholder = placeholder
        self._value.text = self._display_value()

    @property
    def selected(self):
        return self._selected

    def on_release(self):
        if not self._dropdown.parent:
            self._dropdown.open(self)
            self._on_editing(True)

    def _pick(self, value):
        self._dropdown.dismiss()
        self._selected = value
        self._value.text = self._display_value()
        self._on_selected(value)

    def _dismissed(self, *_):
        self._on_editing(False)


class SetupScreen(OnboardingPage):
    """SetupActivity content as a screen. State restores from prefs exactly
    like rememberSaveable reading SharedPreferences; completing the visible
    fields settles for SETUP_SETTLE_MS and then advances once."""

    def __init__(self, helper: SetupHelper, prefs, review_setup=False,
                 accent=None, **kwargs):
        super().__init__(**kwargs)
        self._accent = accent or theme.VIOLET_ACCENT_THEME
        self._helper = helper
        self._prefs = prefs
        self.selected_bank = prefs.get("selected_bank", "") or ""
        self.selected_primary_sim = prefs.get("selected_primary_sim", "") or ""
        # Preserve older installations' hidden SIM preferences without making
        # them setup requirements.
        self.selected_secondary_sim = prefs.get("selected_secondary_sim", "") or ""
        self.is_dual_sim_enabled = bool(prefs.get("is_dual_sim_enabled", False))
        self.disclaimer_accepted = bool(prefs.get("disclaimer_accepted", False))
        self.has_advanced = False
        self.can_advance = not review_setup
        self._editing = set()
        self._advance_event = None

        self.add_content(self._build_heading())
        self.add_content(_spacer(28))
        self.add_content(self._build_selection_card())
        self.add_content(_spacer(16))
        self.add_content(self._build_disclaimer())

    # -- sections ---------------------------------------------------------

    def _build_heading(self):
        box = BoxLayout(orientation="vertical", size_hint=(1, None), spacing=0)
        icon = FloatLayout(size_hint=(1, None), height=dp(48))
        icon.add_widget(Glyph("bank", self._accent.primary,
                              size_hint=(None, None), size=(dp(48), dp(48)),
                              pos_hint={"center_x": 0.5, "y": 0}))
        box.add_widget(icon)
        box.add_widget(_spacer(16))
        title = Label(text=SETUP_TITLE, font_size="31sp", bold=True,
                      color=theme.TEXT_WHITE, size_hint=(1, None),
                      halign="center")
        title.bind(texture_size=lambda w, s: setattr(w, "height", s[1]))
        box.add_widget(title)
        box.add_widget(_spacer(8))
        subtitle = Label(text=SETUP_SUBTITLE, font_size="15sp",
                         color=theme.ONBOARDING_SECONDARY, size_hint=(1, None),
                         halign="center")
        subtitle.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)),
                      texture_size=lambda w, s: setattr(w, "height", s[1]))
        box.add_widget(subtitle)
        box.bind(minimum_height=box.setter("height"))
        return box

    def _build_selection_card(self):
        card = FloatLayout(size_hint=(1, None))
        with card.canvas.before:
            KvColor(rgba=theme.ONBOARDING_SURFACE)
            card._bg = RoundedRectangle(pos=card.pos, size=card.size,
                                        radius=[dp(22)])
        card.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        rows = BoxLayout(orientation="vertical", size_hint=(None, None),
                         spacing=0)
        rows.bind(minimum_height=rows.setter("height"),
                  height=lambda w, h: setattr(card, "height", h),
                  width=lambda w, wd: setattr(card, "width", wd))

        self._bank_row = _SelectionRow(
            "bank", SETUP_BANK_LABEL, self._helper.get_banks(),
            self.selected_bank, self._on_bank, self._editing_changed,
            accent=self._accent, placeholder=SETUP_BANK_PLACEHOLDER)
        rows.add_widget(self._bank_row)

        divider = FloatLayout(size_hint=(1, None), height=dp(1))
        with divider.canvas:
            KvColor(1, 1, 1, 0.08)
            divider._line = RoundedRectangle(pos=(0, 0), size=(0, dp(0.5)),
                                             radius=[0])
        divider.bind(pos=self._layout_divider, size=self._layout_divider)
        rows.add_widget(divider)

        self._sim_row = _SelectionRow(
            "sim", SETUP_SIM_LABEL, self._helper.get_sim_carriers(),
            self.selected_primary_sim, self._on_sim, self._editing_changed,
            accent=self._accent, placeholder=SETUP_SIM_PLACEHOLDER)
        rows.add_widget(self._sim_row)

        card.add_widget(rows)
        card.bind(width=lambda w, wd: setattr(rows, "width", wd),
                  x=lambda w, _: setattr(rows, "x", w.x),
                  y=lambda w, _: setattr(rows, "y", w.y))
        return card

    @staticmethod
    def _layout_divider(divider, *_):
        divider._line.pos = (divider.x + dp(52), divider.y)
        divider._line.size = (max(0, divider.width - dp(52)), dp(0.5))

    def _build_disclaimer(self):
        box = BoxLayout(orientation="vertical", size_hint=(1, None), spacing=0)

        row = BoxLayout(orientation="horizontal", size_hint=(1, None),
                        height=dp(48), spacing=dp(12),
                        padding=(dp(4), dp(4), dp(4), dp(4)))
        self._checkbox = _CheckBox(self.disclaimer_accepted, self._accent,
                                   self._on_disclaimer)
        row.add_widget(self._checkbox)
        text = _left_label(SETUP_ACCEPT, 14, theme.ONBOARDING_BODY)
        text.line_height = 20 / 14
        row.add_widget(text)
        box.add_widget(row)

        self._read_button = Button(text=SETUP_READ, font_size="14sp",
                                   color=self._accent.primary,
                                   size_hint=(None, None), height=dp(48),
                                   background_normal="",
                                   background_color=(0, 0, 0, 0),
                                   halign="left")
        self._read_button.bind(texture_size=lambda w, s: setattr(w, "width", s[0] + dp(4)),
                               on_release=lambda *_: self._toggle_disclaimer_copy())
        read_holder = BoxLayout(orientation="horizontal", size_hint=(1, None),
                                height=dp(48), padding=(dp(40), 0, 0, 0))
        read_holder.add_widget(self._read_button)
        box.add_widget(read_holder)

        self._copy_label = Label(text=DISCLAIMER_TEXT, font_size="13sp",
                                 color=theme.ONBOARDING_SECONDARY,
                                 halign="left", valign="top",
                                 size_hint=(1, None), height=0, opacity=0)
        self._copy_label.line_height = 20 / 13
        self._copy_label.bind(width=lambda *_: self._sync_copy_size())
        box.add_widget(self._copy_label)
        self._disclaimer_expanded = False

        box.bind(minimum_height=box.setter("height"))
        return box

    # -- state changes ------------------------------------------------------

    def _selection(self):
        return SetupData(self.selected_bank, self.selected_primary_sim,
                         self.is_dual_sim_enabled, self.selected_secondary_sim,
                         self.disclaimer_accepted)

    def _advance_state(self):
        selection = self._selection()
        return SetupAdvanceState(
            selection, setup_selection_complete(selection, self._helper),
            self.can_advance, self.has_advanced, bool(self._editing))

    def _editing_changed(self, editing, tag="dropdown"):
        if editing:
            self._editing.add(tag)
        else:
            self._editing.discard(tag)

    def _on_bank(self, value):
        self.selected_bank = value
        self.can_advance = True
        self._maybe_advance()

    def _on_sim(self, value):
        self.selected_primary_sim = value
        self.can_advance = True
        self._maybe_advance()

    def _on_disclaimer(self, value):
        self.disclaimer_accepted = value
        self._checkbox.set_checked(value)
        self.can_advance = True
        self._maybe_advance()

    def _toggle_disclaimer_copy(self):
        self._disclaimer_expanded = not self._disclaimer_expanded
        expanded = self._disclaimer_expanded
        self._read_button.text = SETUP_HIDE if expanded else SETUP_READ
        self._editing_changed(expanded, tag="disclaimer-reading")
        if expanded:
            self._copy_label.opacity = 1
            self._sync_copy_size()
        else:
            self._copy_label.height = 0
            self._copy_label.opacity = 0

    def _sync_copy_size(self):
        # Measure at the live width whenever it changes while expanded.
        if not self._disclaimer_expanded:
            return
        self._copy_label.text_size = (self._copy_label.width - dp(8), None)
        self._copy_label.texture_update()
        self._copy_label.height = self._copy_label.texture_size[1] + dp(16)

    # -- auto-advance (SetupAutoAdvance) -------------------------------------

    def _maybe_advance(self):
        state = self._advance_state()
        if not state.can_proceed():
            return
        if self._advance_event is not None:
            self._advance_event.cancel()
        self._advance_event = Clock.schedule_once(
            lambda *_: self._advance_after_settle(state), SETUP_SETTLE_MS / 1000)

    def _advance_after_settle(self, settled_state):
        self._advance_event = None
        current = self._advance_state()
        if current.can_proceed() and current.selection == settled_state.selection:
            self.has_advanced = True
            self._helper.complete_setup(settled_state.selection)
