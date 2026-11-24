# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/ui/activities/SettingsActivity.kt,
# SettingsComponents.kt, SettingsSheets.kt and SettingsDialogs.kt

"""Settings screen: appearance, payments, permissions, about and app-data
sections, with bottom-sheet pickers and the reset flow.

DEVIATIONS (recorded in MIGRATION.md): ModalBottomSheet becomes a bottom
overlay layer on the screen (same r26 top corners, 80% max height), runtime
permission state comes from an injected provider (all False on desktop —
device-only), the InstallReporter row is gated behind an injectable
predicate (metrics are feature 16), the PrivacyActivity and GitHub intents
are injected callbacks (platform wiring is feature 17), and LazyColumn is a
ScrollView + column.
"""

from kivy.graphics import Color as KvColor, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button, ButtonBehavior
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from paynet import setup as setup_logic
from paynet import theme
from paynet.settings import (BANKS, GITHUB_URL, SIM_NAMES, VERSION_NAME,
                             SettingsRowStyle, SettingsViewModel, sim_name)
from paynet.ui.home import Glyph
from paynet.ui.home_appearance import HomeAppearance

# Section + row copy (settings_refinement_strings.xml / strings.xml).
SECTION_APPEARANCE = "Appearance"
SECTION_PAYMENTS = "Payments"
SECTION_PERMISSIONS = "Permissions"
SECTION_ABOUT = "About PayNet"
SECTION_DATA = "App data"
ROW_HOME_DESIGN = "Home design"
ROW_HOME_COLOR = "Color theme"
HOME_MODERN = "Modern"
HOME_CLASSIC = "Classic"
HOME_MONOCHROME = "Black & White"
HOME_BLUE = "OG Blue"
ROW_BANK = "Bank"
ROW_SIM = "Primary SIM"
ROW_VERSION = "Version"
ROW_PRIVACY = "Privacy"
ROW_PRIVACY_SUMMARY = "Your data and app permissions"
ROW_CLEAR_TITLE = "Clear App Data"
ROW_CLEAR_SUMMARY = "Delete history and reset settings"
PERMISSION_ROWS = [
    ("phone", "Phone", "Set up and make payment calls"),
    ("camera", "Camera", "Scan a UPI QR code"),
    ("contacts", "Contacts", "Choose someone to pay"),
]
ALLOW = "Allow"
SETTINGS_TITLE = "Settings"
SETTINGS_BACK = "Back"

SHEET_OFFICIAL_TITLE = "Official APK"
SHEET_OFFICIAL_MESSAGE = ("This is the official APK distributed by PayNet. It "
                          "does not include SMS parsing. For the SMS parsing "
                          "version, visit our GitHub project.")
SHEET_GITHUB_ACTION = "View on GitHub"
SHEET_RESET_TITLE = "Reset PayNet?"
SHEET_RESET_MESSAGE = ("This permanently deletes your payment history and "
                       "resets all settings. You will return to setup. This "
                       "cannot be undone.")
SHEET_RESET_FAILED = "Couldn't reset PayNet. Please try again."
SHEET_RESETTING = "Resetting..."
SHEET_RESET_ACTION = "Delete all data"
SHEET_CANCEL = "Cancel"


def _left(text, size, color, bold=False):
    label = Label(text=text, font_size=f"{size}sp", color=color, bold=bold,
                  halign="left", valign="middle")
    label.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
    return label


class _BackButton(ButtonBehavior, BoxLayout):
    """SettingsHeading's back TextButton: arrow + 'Back' label, content width."""

    def __init__(self, accent_color, on_back, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("height", dp(48))
        kwargs.setdefault("spacing", dp(6))
        super().__init__(**kwargs)
        self._on_back = on_back
        arrow = FloatLayout(size_hint=(None, None), size=(dp(20), dp(20)),
                            pos_hint={"center_y": 0.5})
        arrow.add_widget(Glyph("back", accent_color, size_hint=(1, 1),
                               pos_hint={"x": 0, "y": 0}))
        self.add_widget(arrow)
        label = _left(SETTINGS_BACK, 16, accent_color)
        label.size_hint_x = None
        label.width = dp(44)
        self.add_widget(label)
        self.width = dp(20) + dp(6) + dp(44) + dp(12)

    def on_release(self):
        self._on_back()


class _Row(ButtonBehavior, BoxLayout):
    """SettingsRow / PermissionRow: icon, title + value column, trailing
    affordance (chevron, swap, check or Allow)."""

    def __init__(self, icon_kind, title, value, style=SettingsRowStyle.STANDARD,
                 on_click=None, trailing=None, accent=None, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint", (1, None))
        kwargs.setdefault("height", dp(72))
        kwargs.setdefault("spacing", dp(16))
        kwargs.setdefault("padding", (dp(16), dp(16), dp(16), dp(16)))
        super().__init__(**kwargs)
        self._on_click = on_click
        accent = accent or theme.VIOLET_ACCENT_THEME
        destructive = style == SettingsRowStyle.DESTRUCTIVE
        icon_color = theme.STATUS_ERROR if destructive else accent.primary

        holder = FloatLayout(size_hint=(None, None), size=(dp(22), dp(22)),
                             pos_hint={"center_y": 0.5})
        holder.add_widget(Glyph(icon_kind, icon_color, size_hint=(1, 1),
                                pos_hint={"x": 0, "y": 0}))
        self.add_widget(holder)

        texts = BoxLayout(orientation="vertical", spacing=dp(4))
        self._title = _left(title, 16,
                            theme.STATUS_ERROR if destructive else theme.TEXT_WHITE)
        self._value = _left(value, 13, theme.TEXT_LIGHT_GRAY)
        self._value.line_height = 18 / 13
        texts.add_widget(self._title)
        texts.add_widget(self._value)
        self.add_widget(texts)

        if trailing == "check":
            check = FloatLayout(size_hint=(None, None), size=(dp(22), dp(22)),
                                pos_hint={"center_y": 0.5})
            check.add_widget(Glyph("check", accent.primary, size_hint=(1, 1),
                                   pos_hint={"x": 0, "y": 0}))
            self.add_widget(check)
        elif trailing == "allow":
            self._allow = Button(text=ALLOW, font_size="14sp",
                                 color=accent.primary, size_hint=(None, None),
                                 size=(dp(64), dp(40)), background_normal="",
                                 background_color=(0, 0, 0, 0),
                                 pos_hint={"center_y": 0.5})
            self._allow.bind(on_release=lambda *_: self._fire())
            self.add_widget(self._allow)
        elif on_click is not None:
            kind = "swap" if style == SettingsRowStyle.CYCLE else "chevron_right"
            tail = FloatLayout(size_hint=(None, None), size=(dp(18), dp(18)),
                               pos_hint={"center_y": 0.5})
            tail.add_widget(Glyph(kind, theme.TEXT_LIGHT_GRAY, size_hint=(1, 1),
                                  pos_hint={"x": 0, "y": 0}))
            self.add_widget(tail)

    def _fire(self):
        if self._on_click is not None:
            self._on_click()

    def on_release(self):
        self._fire()

    def set_value(self, value):
        self._value.text = value


class _GroupCard(FloatLayout):
    """GroupCard: r22 dark container around a measured column of rows."""

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint", (1, None))
        super().__init__(**kwargs)
        with self.canvas.before:
            KvColor(rgba=theme.DARK_GRAY)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size,
                                        radius=[dp(22)])
        self.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        self._column = BoxLayout(orientation="vertical", size_hint=(None, None),
                                 spacing=0)
        self._column.bind(minimum_height=self._column.setter("height"),
                          height=lambda w, h: setattr(self, "height", h),
                          width=lambda w, wd: setattr(self, "width", wd))
        self.add_widget(self._column)
        self.bind(width=lambda w, wd: setattr(self._column, "width", wd),
                  x=lambda w, _: setattr(self._column, "x", w.x),
                  y=lambda w, _: setattr(self._column, "y", w.y))

    def add_row(self, row, divider=True):
        if divider and len(self._column.children) > 0:
            self._column.add_widget(_GroupDivider())
        self._column.add_widget(row)


class _GroupDivider(FloatLayout):
    def __init__(self, indent=56, **kwargs):
        kwargs.setdefault("size_hint", (1, None))
        kwargs.setdefault("height", dp(1))
        super().__init__(**kwargs)
        self._indent = indent
        with self.canvas:
            KvColor(rgba=theme.MEDIUM_GRAY)
            self._line = RoundedRectangle(pos=(0, 0), size=(0, dp(0.5)), radius=[0])
        self.bind(pos=self._layout, size=self._layout)
        self._layout()

    def _layout(self, *_):
        self._line.pos = (self.x + dp(self._indent), self.y)
        self._line.size = (max(0, self.width - dp(self._indent)), dp(0.5))


class _SectionHeader(BoxLayout):
    def __init__(self, title, **kwargs):
        kwargs.setdefault("size_hint", (1, None))
        kwargs.setdefault("height", dp(31))
        kwargs.setdefault("padding", (dp(16), dp(16), 0, dp(2)))
        super().__init__(**kwargs)
        label = _left(title, 13, theme.TEXT_LIGHT_GRAY, bold=True)
        self.add_widget(label)


class _Sheet(FloatLayout):
    """SettingsSheet: bottom overlay, r26 top corners, surface-dim body,
    80% max height. dismissEnabled=False pins it open."""

    def __init__(self, title, on_dismiss, dismiss_enabled=True, **kwargs):
        kwargs.setdefault("size_hint", (1, 1))
        super().__init__(**kwargs)
        self._on_dismiss = on_dismiss
        self._dismiss_enabled = dismiss_enabled
        with self.canvas.before:
            KvColor(0, 0, 0, 0.5)
            self._scrim = RoundedRectangle(pos=self.pos, size=self.size, radius=[0])
        self.bind(pos=lambda w, _: setattr(w._scrim, "pos", w.pos),
                  size=lambda w, _: setattr(w._scrim, "size", w.size))

        self._card = FloatLayout(size_hint=(None, None))
        with self._card.canvas.before:
            KvColor(rgba=theme.SURFACE_DIM)
            self._card_bg = RoundedRectangle(pos=self._card.pos,
                                             size=self._card.size,
                                             radius=[(dp(26), dp(26)), (dp(26), dp(26)), (0, 0), (0, 0)])
        card_bg = self._card_bg
        self._card.bind(pos=lambda w, _: setattr(card_bg, "pos", w.pos),
                        size=lambda w, _: setattr(card_bg, "size", w.size))
        self._body = BoxLayout(orientation="vertical", size_hint=(None, None),
                               spacing=0, padding=(dp(24), dp(20), dp(24), dp(28)))
        self._body.bind(minimum_height=self._body.setter("height"))
        self._body.bind(height=lambda w, h: setattr(self._card, "height", h),
                        width=lambda w, wd: setattr(self._card, "width", wd))
        title_label = _left(title, 20, theme.TEXT_WHITE, bold=True)
        title_label.size_hint_y = None
        title_label.height = dp(28)
        self._body.add_widget(title_label)
        self._body.add_widget(BoxLayout(size_hint=(1, None), height=dp(20)))
        self._content = BoxLayout(orientation="vertical", size_hint=(1, None),
                                  spacing=0)
        self._content.bind(minimum_height=self._content.setter("height"))
        self._body.add_widget(self._content)
        self._card.add_widget(self._body)
        self.add_widget(self._card)
        self.bind(pos=self._relayout, size=self._relayout)
        self._relayout()

    def _relayout(self, *_):
        self._body.width = self.width
        self._card.height = min(self._card.height or 0, self.height * 0.80)
        self._card.pos = (self.x, self.y)
        self._body.pos = self._card.pos

    def add_content(self, widget):
        self._content.add_widget(widget)

    def on_touch_down(self, touch):
        if self._dismiss_enabled and not self._card.collide_point(*touch.pos):
            self._on_dismiss()
            return True
        return super().on_touch_down(touch)


class _ChoiceGroup(FloatLayout):
    """SettingsChoiceGroup: r16 dark container with radio-style choices."""

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint", (1, None))
        super().__init__(**kwargs)
        with self.canvas.before:
            KvColor(rgba=theme.DARK_GRAY)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size,
                                        radius=[dp(16)])
        self.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        self._column = BoxLayout(orientation="vertical", size_hint=(None, None),
                                 spacing=0)
        self._column.bind(minimum_height=self._column.setter("height"),
                          height=lambda w, h: setattr(self, "height", h),
                          width=lambda w, wd: setattr(self, "width", wd))
        self.add_widget(self._column)
        self.bind(width=lambda w, wd: setattr(self._column, "width", wd),
                  x=lambda w, _: setattr(self._column, "x", w.x),
                  y=lambda w, _: setattr(self._column, "y", w.y))

    def add_choice(self, row, divider=True):
        if divider and len(self._column.children) > 0:
            self._column.add_widget(_GroupDivider(indent=16))
        self._column.add_widget(row)


class _ChoiceRow(ButtonBehavior, BoxLayout):
    """SettingsChoice: optional swatch, title (+subtitle), check when picked."""

    def __init__(self, title, selected, on_click, subtitle=None, accent=None,
                 **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint", (1, None))
        kwargs.setdefault("height", dp(58) if not subtitle else dp(76))
        kwargs.setdefault("spacing", dp(12))
        kwargs.setdefault("padding", (dp(16), dp(14), dp(16), dp(14)))
        super().__init__(**kwargs)
        self._on_click = on_click
        accent = accent or theme.VIOLET_ACCENT_THEME
        texts = BoxLayout(orientation="vertical", spacing=dp(4))
        texts.add_widget(_left(title, 16, theme.TEXT_WHITE))
        if subtitle:
            texts.add_widget(_left(subtitle, 13, theme.TEXT_LIGHT_GRAY))
        self.add_widget(texts)
        if selected:
            check = FloatLayout(size_hint=(None, None), size=(dp(19), dp(19)),
                                pos_hint={"center_y": 0.5})
            check.add_widget(Glyph("check", accent.primary, size_hint=(1, 1),
                                   pos_hint={"x": 0, "y": 0}))
            self.add_widget(check)

    def on_release(self):
        self._on_click()


class SettingsScreen(FloatLayout):
    """SettingsActivity content. Owns its SettingsViewModel; the app shell
    supplies stores and navigation callbacks."""

    def __init__(self, prefs, settings_repository, test_results,
                 transaction_repository, on_back, on_open_setup,
                 on_appearance_changed=None, on_open_privacy=None,
                 on_open_link=None, permission_provider=None,
                 install_reporter_configured=None, on_open_install_count=None,
                 accent=None, **kwargs):
        kwargs.setdefault("size_hint", (1, 1))
        super().__init__(**kwargs)
        self._accent = accent or theme.VIOLET_ACCENT_THEME
        self._prefs = prefs
        self._settings_repository = settings_repository
        self._test_results = test_results
        self._transactions = transaction_repository
        self._on_back = on_back
        self._on_open_setup = on_open_setup
        self._on_appearance_changed = on_appearance_changed or (lambda: None)
        self._on_open_privacy = on_open_privacy or (lambda: None)
        self._on_open_link = on_open_link or (lambda _url: None)
        self._permission_provider = permission_provider or (lambda: {
            "phone": False, "camera": False, "contacts": False, "overlay": False})
        self._install_reporter_configured = install_reporter_configured or (lambda: False)
        self._on_open_install_count = on_open_install_count or (lambda: None)
        self.view_model = SettingsViewModel()
        self._sheet = None
        self._appearance = HomeAppearance.read(prefs)

        with self.canvas.before:
            KvColor(0, 0, 0, 1)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[0])
        self.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))

        self._scroll = ScrollView(size_hint=(1, 1))
        self._column = BoxLayout(orientation="vertical", size_hint=(1, None),
                                 spacing=dp(10),
                                 padding=(dp(24), dp(8), dp(24), dp(32)))
        self._column.bind(minimum_height=self._column.setter("height"))
        self._scroll.add_widget(self._column)
        self.add_widget(self._scroll)
        self._build()

    def refresh(self):
        """LaunchedEffect(repository) + onResume: re-read every source."""
        self._appearance = HomeAppearance.read(self._prefs)
        self._close_sheet()
        self._column.clear_widgets()
        self._build()

    # -- construction ---------------------------------------------------------

    def _build(self):
        self.view_model.load_from_repository(self._settings_repository, self._prefs)
        self.view_model.refresh_permissions(self._permission_provider)
        state = self.view_model.state

        self._column.add_widget(self._build_heading())

        self._column.add_widget(_SectionHeader(SECTION_APPEARANCE))
        appearance_card = _GroupCard()
        self._design_row = _Row(
            "dashboard", ROW_HOME_DESIGN,
            HOME_CLASSIC if self._appearance.classic else HOME_MODERN,
            style=SettingsRowStyle.CYCLE, on_click=self._toggle_design,
            accent=self._accent)
        appearance_card.add_row(self._design_row, divider=False)
        self._color_row = _Row(
            "palette", ROW_HOME_COLOR,
            HOME_MONOCHROME if self._appearance.monochrome else HOME_BLUE,
            style=SettingsRowStyle.CYCLE, on_click=self._toggle_color,
            accent=self._accent)
        appearance_card.add_row(self._color_row)
        self._column.add_widget(appearance_card)

        self._column.add_widget(_SectionHeader(SECTION_PAYMENTS))
        payments_card = _GroupCard()
        self._bank_row = _Row("bank", ROW_BANK, state.selected_bank.name,
                              on_click=lambda: self._open_sheet("bank"),
                              accent=self._accent)
        payments_card.add_row(self._bank_row, divider=False)
        self._sim_row = _Row("sim", ROW_SIM,
                             sim_name(self._prefs.get("selected_primary_sim", "") or ""),
                             on_click=lambda: self._open_sheet("sim"),
                             accent=self._accent)
        payments_card.add_row(self._sim_row)
        self._column.add_widget(payments_card)

        self._column.add_widget(_SectionHeader(SECTION_PERMISSIONS))
        permissions_card = _GroupCard()
        for index, (key, title, subtitle) in enumerate(PERMISSION_ROWS):
            granted = state.permissions.get(key) is True
            permissions_card.add_row(
                _Row({"phone": "phone", "camera": "camera",
                      "contacts": "person"}[key], title, subtitle,
                     on_click=None if granted else self._request_permissions,
                     trailing="check" if granted else "allow",
                     accent=self._accent),
                divider=index > 0)
        self._column.add_widget(permissions_card)

        self._column.add_widget(_SectionHeader(SECTION_ABOUT))
        about_card = _GroupCard()
        about_card.add_row(_Row("info", ROW_VERSION, VERSION_NAME,
                                on_click=lambda: self._open_sheet("version"),
                                accent=self._accent), divider=False)
        if self._install_reporter_configured():
            about_card.add_row(_Row("dashboard", "Installation count",
                                    "Manage optional reporting",
                                    on_click=self._on_open_install_count,
                                    accent=self._accent))
        about_card.add_row(_Row("shield", ROW_PRIVACY, ROW_PRIVACY_SUMMARY,
                                on_click=self._on_open_privacy,
                                accent=self._accent))
        self._column.add_widget(about_card)

        self._column.add_widget(_SectionHeader(SECTION_DATA))
        data_card = _GroupCard()
        data_card.add_row(_Row("trash", ROW_CLEAR_TITLE, ROW_CLEAR_SUMMARY,
                               style=SettingsRowStyle.DESTRUCTIVE,
                               on_click=lambda: self._open_sheet("clear"),
                               accent=self._accent), divider=False)
        self._column.add_widget(data_card)

    def _build_heading(self):
        row = BoxLayout(orientation="horizontal", size_hint=(1, None),
                        height=dp(48))
        back = _BackButton(self._accent.primary, self._on_back)
        row.add_widget(back)
        row.add_widget(BoxLayout())
        gear = FloatLayout(size_hint=(None, None), size=(dp(26), dp(26)),
                           pos_hint={"center_y": 0.5})
        gear.add_widget(Glyph("gear", self._accent.primary, size_hint=(1, 1),
                              pos_hint={"x": 0, "y": 0}))
        row.add_widget(gear)
        return row

    # -- appearance toggles -----------------------------------------------------

    def _toggle_design(self):
        self._appearance = HomeAppearance(
            classic=not self._appearance.classic,
            monochrome=self._appearance.monochrome)
        self._appearance.save(self._prefs)
        self._design_row.set_value(
            HOME_CLASSIC if self._appearance.classic else HOME_MODERN)
        self._on_appearance_changed()

    def _toggle_color(self):
        self._appearance = HomeAppearance(
            classic=self._appearance.classic,
            monochrome=not self._appearance.monochrome)
        self._appearance.save(self._prefs)
        self._color_row.set_value(
            HOME_MONOCHROME if self._appearance.monochrome else HOME_BLUE)
        self._on_appearance_changed()

    # -- sheets --------------------------------------------------------------------

    def _open_sheet(self, kind):
        self._close_sheet()
        if kind == "version":
            sheet = _Sheet(SHEET_OFFICIAL_TITLE, self._close_sheet)
            message = _left(SHEET_OFFICIAL_MESSAGE, 15, theme.TEXT_PALE)
            message.line_height = 22 / 15
            message.size_hint_y = None
            message.bind(texture_size=lambda w, s: setattr(w, "height", s[1]))
            sheet.add_content(message)
            sheet.add_content(BoxLayout(size_hint=(1, None), height=dp(22)))
            group = _ChoiceGroup()
            link = _Row("open_in_new", SHEET_GITHUB_ACTION, "",
                        on_click=lambda: self._on_open_link(GITHUB_URL),
                        accent=self._accent)
            link.height = dp(56)
            group.add_choice(link, divider=False)
            sheet.add_content(group)
        elif kind == "bank":
            sheet = _Sheet(ROW_BANK, self._close_sheet)
            group = _ChoiceGroup()
            current = self.view_model.state.selected_bank.id
            for index, bank in enumerate(BANKS):
                group.add_choice(
                    _ChoiceRow(bank.name, bank.id == current,
                               lambda b=bank: self._pick_bank(b),
                               accent=self._accent),
                    divider=index > 0)
            sheet.add_content(group)
        elif kind == "sim":
            sheet = _Sheet(ROW_SIM, self._close_sheet)
            group = _ChoiceGroup()
            current_sim = self._prefs.get("selected_primary_sim", "") or ""
            for index, (sid, name) in enumerate(SIM_NAMES):
                group.add_choice(
                    _ChoiceRow(name, sid == current_sim,
                               lambda s=sid: self._pick_sim(s),
                               accent=self._accent),
                    divider=index > 0)
            sheet.add_content(group)
        else:  # clear
            sheet = _Sheet(SHEET_RESET_TITLE, self._close_sheet,
                           dismiss_enabled=not self.view_model.is_resetting)
            message = _left(SHEET_RESET_MESSAGE, 15, theme.TEXT_PALE)
            message.line_height = 22 / 15
            message.size_hint_y = None
            message.bind(texture_size=lambda w, s: setattr(w, "height", s[1]))
            sheet.add_content(message)
            sheet.add_content(BoxLayout(size_hint=(1, None), height=dp(20)))
            if self.view_model.reset_failed:
                error = _left(SHEET_RESET_FAILED, 14, theme.STATUS_ERROR)
                error.line_height = 20 / 14
                error.size_hint_y = None
                error.height = dp(20)
                sheet.add_content(error)
                sheet.add_content(BoxLayout(size_hint=(1, None), height=dp(12)))
            buttons = BoxLayout(orientation="horizontal", spacing=dp(8),
                                size_hint=(1, None), height=dp(48))
            cancel = Button(text=SHEET_CANCEL, font_size="15sp",
                            color=theme.TEXT_WHITE, background_normal="",
                            background_color=(0, 0, 0, 0),
                            disabled=self.view_model.is_resetting)
            cancel.bind(on_release=lambda *_: self._close_sheet())
            buttons.add_widget(cancel)
            confirm = Button(
                text=SHEET_RESETTING if self.view_model.is_resetting else SHEET_RESET_ACTION,
                font_size="15sp", bold=True, color=theme.STATUS_ERROR,
                background_normal="", background_color=(0, 0, 0, 0),
                disabled=self.view_model.is_resetting)
            confirm.bind(on_release=lambda *_: self._confirm_clear())
            buttons.add_widget(confirm)
            sheet.add_content(buttons)
        self._sheet = sheet
        self.add_widget(sheet)

    def _close_sheet(self):
        if self._sheet is not None:
            self.remove_widget(self._sheet)
            self._sheet = None

    # -- actions ---------------------------------------------------------------------

    def _pick_bank(self, bank):
        if (self._prefs.get("selected_bank", "") or "") != bank.id:
            setup_logic.invalidate_payment_configuration(
                self._prefs, self._test_results)
        self.view_model.update_bank(bank)
        saved = self._settings_repository.settings
        saved.bankId = bank.id
        self._settings_repository.save_settings(saved)
        self._prefs.put("selected_bank", bank.id)
        self._bank_row.set_value(bank.name)
        self._close_sheet()

    def _pick_sim(self, sim_id):
        if (self._prefs.get("selected_primary_sim", "") or "") != sim_id:
            setup_logic.invalidate_payment_configuration(
                self._prefs, self._test_results)
        self._prefs.put("selected_primary_sim", sim_id)
        self._sim_row.set_value(sim_name(sim_id))
        self._close_sheet()

    def _request_permissions(self):
        # Runtime permission prompts are device-only (feature 17); the
        # provider reports the honest state on desktop.
        self.view_model.refresh_permissions(self._permission_provider)

    def _confirm_clear(self):
        def reset():
            return _reset_settings_data(
                delete_transactions=self._transactions.delete_all_transactions,
                clear_preferences=self._clear_preferences,
                open_setup=self._on_open_setup)

        self.view_model.reset_data(reset)
        if self.view_model.reset_failed:
            self._open_sheet("clear")  # re-show with the failure line
        else:
            self._close_sheet()

    def _clear_preferences(self):
        self._settings_repository.clear_all_data()
        self._prefs.clear()


def _reset_settings_data(delete_transactions, clear_preferences, open_setup):
    """paynet.settings.reset_settings_data bound to the screen's stores."""
    from paynet.settings import reset_settings_data
    return reset_settings_data(delete_transactions, clear_preferences, open_setup)
