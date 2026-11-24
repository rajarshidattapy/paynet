# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/MainScreenContent.kt,
# app/src/main/java/com/paynet/app/ui/home/HomeDashboard.kt and
# app/src/main/java/com/paynet/app/ui/home/ModernHistoryPanel.kt

"""Home dashboard (modern variant) as Kivy widgets.

The Compose layout's sizing formulas are ported exactly (max content width
440dp, tile width clamp, hero height, insets, fixed history panel with its
32dp extension and floating scan action). The wordmark renders the same
source PNG with the same crop rect as the Compose Canvas.

Known rendering approximations (recorded in MIGRATION.md): the Material
vector icons (QR, arrow, settings gear) become simple canvas-drawn glyphs
until the asset pipeline lands; the classic dashboard variant ships with
the rest of feature 8.
"""

from __future__ import annotations

import os
from typing import Callable, List, Optional

from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from .. import theme
from ..db.models import PaymentDetails, PaymentStatus
from ..utils.dates import format_date

# strings.xml values used on this screen.
STR_TAGLINE = "UPI payments, even offline"
STR_CONNECTED_BANK = "Connected bank"
STR_SETTINGS = "Settings"
STR_SEND = "Send money"
STR_SCAN = "Scan QR"
STR_SCAN_TO_PAY = "Scan to pay"
STR_RECENT = "Recent payments"
STR_VIEW_ALL = "View all"
STR_EMPTY = "No payments yet"
STR_RETRY = "Retry"
STR_ERROR_LOAD = "Could not load your transactions."
STR_READY = "Ready"
STR_SETUP_REQUIRED = "Payment setup required"
STR_OPENING = "Opening scanner"
STR_RECIPIENT_UNKNOWN = "Not recorded"
STR_CONFIRMED = "Confirmed by you"
STR_NOT_CONFIRMED = "Not confirmed by you"
STR_PENDING = "Awaiting your confirmation"
STR_UNVERIFIED = "Unverified"
STR_SUCCESS = "Success"
STR_FAILED = "Failed"

_BANK_NAMES = {
    "sbi": "State Bank of India",
    "hdfc": "HDFC Bank",
    "icici": "ICICI Bank",
    "axis": "Axis Bank",
    "kotak": "Kotak Mahindra Bank",
    "pnb": "Punjab National Bank",
    "bob": "Bank of Baroda",
    "yes": "Yes Bank",
    "idbi": "IDBI Bank",
    "canara": "Canara Bank",
}


def home_bank_name(bank: str) -> str:
    return _BANK_NAMES.get(bank, "HDFC Bank")


def _gradient_texture(top_rgba, bottom_rgba) -> Texture:
    """A 1x2 vertical gradient texture (Kivy has no built-in gradient)."""
    texture = Texture.create(size=(1, 2), colorfmt="rgba")
    px = bytes(
        [int(c * 255) for c in bottom_rgba] + [int(c * 255) for c in top_rgba]
    )
    texture.blit_buffer(px, colorfmt="rgba", bufferfmt="ubyte")
    texture.wrap = "clamp_to_edge"
    return texture


def _crop_region(image_path: str, x: int, y: int, w: int, h: int):
    """The Compose Canvas crop (srcOffset/srcSize), with Kivy's bottom-left
    texture origin."""
    from kivy.core.image import Image as CoreImage

    texture = CoreImage.load(image_path).texture
    flipped_y = texture.height - y - h
    return texture.get_region(x, flipped_y, w, h)


class RoundedBox(FloatLayout):
    """A rounded-rect background (optionally a two-stop vertical gradient)."""

    def __init__(self, bg=None, radius=24, gradient=None, **kwargs):
        super().__init__(**kwargs)
        self._radius = radius
        self._bg = bg
        self._gradient = gradient
        with self.canvas.before:
            self._color = Color(rgba=(0, 0, 0, 0))
            self._shape = RoundedRectangle(pos=self.pos, size=self.size, radius=[(radius,)] * 4)
        self.bind(pos=self._relayout, size=self._relayout)
        self._relayout()

    def _relayout(self, *_):
        if self._gradient is not None:
            self._shape.texture = _gradient_texture(*self._gradient)
            self._color.rgba = (1, 1, 1, 1)
        elif self._bg is not None:
            self._color.rgba = self._bg
        self._shape.pos = self.pos
        self._shape.size = self.size


class Glyph(Widget):
    """A simple canvas-drawn icon (arrow-outward / QR / gear / check /
    close / person) standing in for the Material vector assets."""

    def __init__(self, kind: str, ink, **kwargs):
        super().__init__(**kwargs)
        self._kind = kind
        self._ink = ink
        self.bind(pos=self._draw, size=self._draw)
        self._draw()

    def _draw(self, *_):
        self.canvas.clear()
        w, h = self.size
        x, y = self.pos
        with self.canvas:
            Color(rgba=self._ink)
            lw = max(dp(1.6), min(w, h) * 0.09)
            if self._kind == "arrow":
                # Outward arrow: shaft bottom-left -> top-right plus head.
                Line(points=[x + w * .2, y + h * .2, x + w * .8, y + h * .8], width=lw, cap="round")
                Line(points=[x + w * .38, y + h * .8, x + w * .8, y + h * .8], width=lw, cap="round")
                Line(points=[x + w * .8, y + h * .8, x + w * .8, y + h * .38], width=lw, cap="round")
            elif self._kind == "qr":
                s = w * .26
                for cx, cy in ((0.06, 0.68), (0.68, 0.68), (0.06, 0.06)):
                    Line(rectangle=(x + w * cx, y + h * cy, s, s), width=lw)
                Rectangle(pos=(x + w * .68, y + h * .06), size=(s * .8, s * .8))
            elif self._kind == "gear":
                Ellipse(pos=(x + w * .3, y + h * .3), size=(w * .4, h * .4))
                Line(circle=(x + w * .5, y + h * .5, w * .42), width=lw)
            elif self._kind == "check":
                Line(points=[x + w * .18, y + h * .5, x + w * .42, y + h * .26,
                             x + w * .82, y + h * .74], width=lw, cap="round")
            elif self._kind == "close":
                Line(points=[x + w * .22, y + h * .22, x + w * .78, y + h * .78], width=lw, cap="round")
                Line(points=[x + w * .22, y + h * .78, x + w * .78, y + h * .22], width=lw, cap="round")
            elif self._kind == "person":
                Ellipse(pos=(x + w * .3, y + h * .55), size=(w * .4, h * .4))
                Ellipse(pos=(x + w * .12, y + h * .02), size=(w * .76, h * .42))
            elif self._kind == "history":
                Line(circle=(x + w * .5, y + h * .5, w * .4), width=lw)
                Line(points=[x + w * .5, y + h * .5, x + w * .5, y + h * .78], width=lw)
                Line(points=[x + w * .5, y + h * .5, x + w * .72, y + h * .44], width=lw)


class ActionTile(ButtonBehavior, RoundedBox):
    """HomeAction: rounded tile with a centred glyph; state is exposed for
    accessibility/testing via .state_text."""

    def __init__(self, label: str, kind: str, bg, ink, state: str = "",
                 enabled: bool = True, corner: float = 28, round_tile: bool = False,
                 icon_fraction: float = 0.42, on_press=None, **kwargs):
        super().__init__(bg=bg, radius=corner, **kwargs)
        self.label_text = label
        self.state_text = state
        self.disabled = not enabled
        self._on_press = on_press
        # pos_hint lets the FloatLayout keep the glyph centred; only the
        # size needs manual tracking.
        self._glyph = Glyph(kind, ink, size_hint=(None, None),
                            pos_hint={"center_x": 0.5, "center_y": 0.5})
        self.add_widget(self._glyph)
        self._round = round_tile
        self._icon_fraction = icon_fraction
        self.bind(size=self._place)
        self._place()

    def _place(self, *_):
        side = min(self.size) * self._icon_fraction
        self._glyph.size = (side, side)
        if self._round:
            self._shape.radius = [(min(self.size) / 2,)] * 4 if hasattr(self._shape, "radius") else self._shape.radius

    def on_release(self):
        if not self.disabled and self._on_press is not None:
            self._on_press()


class BrandCard(RoundedBox):
    """The web-variant brand card: gradient, wordmark, tagline, connected
    bank, settings action (top-end)."""

    def __init__(self, bank: str, monochrome: bool, on_settings: Callable[[], None], **kwargs):
        palette = theme.accent_theme_for(monochrome)
        gradient = (
            (theme.HOME_PEARL_GRADIENT_START, theme.HOME_PEARL_GRADIENT_END)
            if monochrome
            else (palette.header_gradient_start, palette.header_gradient_end)
        )
        super().__init__(radius=28, gradient=gradient, **kwargs)
        ink = theme.HOME_WEB_INK if monochrome else (1, 1, 1, 1)
        muted = theme.HOME_WEB_TAGLINE if monochrome else (1, 1, 1, 0.82)

        root = BoxLayout(orientation="vertical", padding=[dp(24), dp(24), dp(24), dp(24)])
        top = FloatLayout(size_hint_y=None, height=dp(32))
        assets = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        wordmark_src = os.path.join(
            assets,
            "home_wordmark_white_source.png" if not monochrome else "home_wordmark_source.png",
        )
        if os.path.exists(wordmark_src):
            if monochrome:
                region = _crop_region(wordmark_src, 82, 182, 382, 90)
            else:
                region = _crop_region(wordmark_src, 16, 161, 539, 123)
            wordmark = Image(
                texture=region, size_hint=(None, None), size=(dp(116), dp(32)),
                pos_hint={"x": 0, "center_y": 0.5}, allow_stretch=True, keep_ratio=True,
            )
            top.add_widget(wordmark)
        else:
            top.add_widget(
                Label(text="PayNet", bold=True, font_size="20sp", color=ink,
                      size_hint=(None, 1), pos_hint={"x": 0})
            )
        settings_btn = ActionTile(
            STR_SETTINGS, "gear", bg=(1, 1, 1, 0.3),
            ink=(theme.HOME_WEB_SETTINGS if monochrome else ink),
            corner=15, icon_fraction=0.5, size_hint=(None, None), size=(dp(30), dp(30)),
            pos_hint={"right": 1, "center_y": 0.5}, on_press=on_settings,
        )
        top.add_widget(settings_btn)
        root.add_widget(top)

        root.add_widget(
            Label(text=STR_TAGLINE, color=muted, font_size="13sp",
                  size_hint_y=None, height=dp(20), halign="left", valign="middle")
        )
        root.add_widget(Widget())  # spacer

        bank_block = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(52),
                               spacing=dp(5))
        bank_lbl = Label(text=STR_CONNECTED_BANK, color=muted, font_size="11sp",
                         size_hint_y=None, height=dp(16), halign="left")
        name_lbl = Label(text=bank, color=ink, font_size="18sp", bold=True,
                         size_hint_y=None, height=dp(26), halign="left", valign="bottom")
        for lbl in (bank_lbl, name_lbl):
            lbl.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
        bank_block.add_widget(bank_lbl)
        bank_block.add_widget(name_lbl)
        root.add_widget(bank_block)
        self.add_widget(root)
        # FloatLayout children default to window (0,0): track the card.
        self.bind(pos=lambda *_: setattr(root, "pos", self.pos))


class PaymentRow(ButtonBehavior, BoxLayout):
    """ModernPaymentRow: recipient + date left, status glyph right."""

    def __init__(self, payment: PaymentDetails, on_press=None, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(90),
                         padding=[0, dp(16), 0, dp(16)], spacing=dp(12), **kwargs)
        self.payment = payment
        self._on_press = on_press

        text_col = BoxLayout(orientation="vertical", spacing=dp(4))
        recipient = Label(
            text=payment.recipient_label or STR_RECIPIENT_UNKNOWN,
            color=theme.HOME_HISTORY_TEXT, font_size="17sp", bold=True,
            halign="left", valign="middle", shorten=True, shorten_from="right",
        )
        date = Label(
            text=format_date(payment.timestamp), color=theme.HOME_HISTORY_MUTED,
            font_size="13sp", halign="left", valign="middle",
        )
        for lbl in (recipient, date):
            lbl.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
        text_col.add_widget(recipient)
        text_col.add_widget(date)
        self.add_widget(text_col)

        if payment.userConfirmed is None:
            kind = "arrow"
            self.status_text = self._status_label(payment)
        elif payment.userConfirmed:
            kind = "check"
            self.status_text = STR_CONFIRMED
        else:
            kind = "close"
            self.status_text = STR_NOT_CONFIRMED
        status = Glyph(kind, theme.HOME_HISTORY_MUTED, size_hint=(None, None),
                       size=(dp(16), dp(16)), pos_hint={"center_y": 0.5})
        self.add_widget(status)

    @staticmethod
    def _status_label(payment: PaymentDetails) -> str:
        if payment.status == PaymentStatus.COMPLETED:
            return STR_SUCCESS
        if payment.status == PaymentStatus.FAILED:
            return STR_FAILED
        if payment.status == PaymentStatus.PENDING:
            return STR_PENDING
        return STR_UNVERIFIED

    def on_release(self):
        if self._on_press is not None:
            self._on_press(self.payment)


class ModernHistoryPanel(RoundedBox):
    """ModernRecentPayments: fixed-height panel, header, list, floating
    scan action."""

    SCAN_SIZE = 62
    PANEL_EXTENSION = 32
    SCAN_BOTTOM = 36 + PANEL_EXTENSION
    LIST_BOTTOM_INSET = 24

    def __init__(self, control, ink, on_history=None, on_retry=None,
                 on_transaction=None, on_scan=None, **kwargs):
        super().__init__(bg=theme.HOME_MODERN_HISTORY, radius=28, **kwargs)
        self._control = control
        self._ink = ink
        self._on_history = on_history
        self._on_retry = on_retry
        self._on_transaction = on_transaction
        self._on_scan = on_scan
        self._scan_state = STR_READY
        self._scan_enabled = True

        self._content = BoxLayout(
            orientation="vertical",
            padding=[dp(24), dp(24), dp(24), dp(self.LIST_BOTTOM_INSET)],
        )
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44))
        title = Label(text=STR_RECENT, color=theme.HOME_HISTORY_TEXT, font_size="20sp",
                      bold=True, halign="left", valign="middle")
        title.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
        header.add_widget(title)
        header.add_widget(_TextButton(STR_VIEW_ALL, on_history))
        self._content.add_widget(header)
        self._content.add_widget(Widget(size_hint_y=None, height=dp(10)))

        self._scroll = ScrollView()
        self._rows = BoxLayout(orientation="vertical", size_hint_y=None)
        self._rows.bind(minimum_height=self._rows.setter("height"))
        self._scroll.add_widget(self._rows)
        self._content.add_widget(self._scroll)
        self.add_widget(self._content)
        # FloatLayout children default to window (0,0): track the panel.
        self.bind(pos=lambda *_: setattr(self._content, "pos", self.pos))

        self._scan = ActionTile(
            STR_SCAN_TO_PAY, "qr", bg=control, ink=ink, corner=31, round_tile=True,
            icon_fraction=0.48, size_hint=(None, None), size=(dp(self.SCAN_SIZE), dp(self.SCAN_SIZE)),
            pos_hint={"center_x": 0.5, "y": 0}, on_press=self._scan_pressed,
        )
        self._scan.y = dp(self.SCAN_BOTTOM)
        self.add_widget(self._scan)

    def set_scan_state(self, state: str, enabled: bool) -> None:
        self._scan_state = state
        self._scan_enabled = enabled
        self._scan.disabled = not enabled
        self._scan.state_text = state

    def _scan_pressed(self):
        if self._on_scan is not None:
            self._on_scan()

    def show_loading(self) -> None:
        self._rows.clear_widgets()
        self._rows.add_widget(
            Label(text="…", color=self._control, font_size="24sp",
                  size_hint_y=None, height=dp(170))
        )

    def show_error(self) -> None:
        self._rows.clear_widgets()
        self._rows.add_widget(
            Label(text=STR_ERROR_LOAD, color=theme.HOME_MUTED, font_size="14sp",
                  size_hint_y=None, height=dp(30))
        )
        retry_anchor = AnchorLayout(anchor_x="center", size_hint_y=None, height=dp(30))
        retry_anchor.add_widget(_TextButton(STR_RETRY, self._on_retry, height=dp(30)))
        self._rows.add_widget(retry_anchor)

    def show_payments(self, payments: List[PaymentDetails]) -> None:
        self._rows.clear_widgets()
        if not payments:
            empty = FloatLayout(size_hint_y=None, height=dp(208))
            icon = Glyph("history", theme.HOME_MUTED, size_hint=(None, None),
                         size=(dp(24), dp(24)), pos_hint={"center_x": 0.5, "center_y": 0.62})
            empty.add_widget(icon)
            empty.add_widget(
                Label(text=STR_EMPTY, color=theme.HOME_MUTED, font_size="16sp",
                      size_hint=(1, None), height=dp(24), pos_hint={"center_x": 0.5, "center_y": 0.34})
            )
            self._rows.add_widget(empty)
            return
        for payment in payments:
            self._rows.add_widget(PaymentRow(payment, on_press=self._on_transaction))


class _TextButton(ButtonBehavior, Label):
    def __init__(self, text: str, on_press=None, height=None, **kwargs):
        kwargs.setdefault("color", theme.HOME_MUTED)
        kwargs.setdefault("font_size", "12.5sp")
        kwargs.setdefault("size_hint", (None, None))
        super().__init__(text=text, **kwargs)
        self._on_press = on_press
        self.height = height or dp(44)
        self.bind(texture_size=self._sync_width)
        self._sync_width()

    def _sync_width(self, *_):
        # No text_size constraint: the texture is the natural text width, so
        # binding width to it cannot feed back into a relayout loop.
        self.width = self.texture_size[0] + dp(12)

    def on_release(self):
        if self._on_press is not None:
            self._on_press()


class HomeScreen(FloatLayout):
    """The modern home dashboard. Sizing formulas ported 1:1 from
    HomeDashboard.kt's BoxWithConstraints block."""

    MAX_CONTENT_WIDTH = 440

    def __init__(
        self,
        bank_id: str = "hdfc",
        monochrome: bool = True,
        is_upi123_ready: bool = False,
        is_ussd_ready: bool = False,
        is_scanning: bool = False,
        on_settings=None,
        on_history=None,
        on_retry=None,
        on_transaction=None,
        on_scan=None,
        on_pay_contact=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.bank_id = bank_id
        self.monochrome = monochrome
        self.is_upi123_ready = is_upi123_ready
        self.is_ussd_ready = is_ussd_ready
        self.is_scanning = is_scanning
        palette = theme.accent_theme_for(monochrome)
        self._controls = theme.HOME_PEARL if monochrome else palette.header_gradient_end
        self._control_ink = theme.HOME_CONTROL_INK if monochrome else (1, 1, 1, 1)
        canvas_bg = theme.HOME_MODERN_CANVAS

        with self.canvas.before:
            Color(rgba=canvas_bg)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda *_: setattr(self._bg_rect, "pos", self.pos),
                  size=lambda *_: setattr(self._bg_rect, "size", self.size))

        self._on_scan = on_scan
        self._on_pay_contact = on_pay_contact

        self._root = BoxLayout(orientation="vertical", spacing=dp(32))
        self.add_widget(self._root)

        self.brand_card = BrandCard(
            home_bank_name(bank_id), monochrome, on_settings or (lambda: None),
            size_hint=(1, 1),
        )
        self.send_tile = ActionTile(
            STR_SEND, "arrow", self._controls, self._control_ink,
            state=self._pay_state(), corner=28, on_press=on_pay_contact,
        )
        self.scan_tile = ActionTile(
            STR_SCAN, "qr", self._controls, self._control_ink,
            state=self._scan_state(), corner=28, on_press=on_scan,
        )
        self.history_panel = ModernHistoryPanel(
            self._controls, self._control_ink,
            on_history=on_history, on_retry=on_retry,
            on_transaction=on_transaction, on_scan=on_scan,
        )
        self.history_panel.set_scan_state(self._scan_state(), not is_scanning)

        self._hero = BoxLayout(orientation="horizontal", spacing=dp(12), size_hint_y=None)
        tiles = BoxLayout(orientation="vertical", spacing=dp(12), size_hint_x=None)
        tiles.add_widget(self.send_tile)
        tiles.add_widget(self.scan_tile)
        self._hero.add_widget(self.brand_card)
        self._hero.add_widget(tiles)
        self._tiles = tiles

        self._root.add_widget(self._hero)
        self._root.add_widget(self.history_panel)

        self.bind(size=self._relayout, pos=self._relayout)
        self._relayout()

    def _scan_state(self) -> str:
        if self.is_scanning:
            return STR_OPENING
        return STR_READY if self.is_ussd_ready else STR_SETUP_REQUIRED

    def _pay_state(self) -> str:
        return STR_READY if self.is_upi123_ready else STR_SETUP_REQUIRED

    def _relayout(self, *_):
        w, h = self.size
        if w <= 0 or h <= 0:
            return
        content_width = min(w, dp(self.MAX_CONTENT_WIDTH))
        tile_width = min(max(content_width * 0.26, dp(88)), dp(116))
        extra_height = min(max((h - dp(700)) * 0.16, 0), dp(18))
        hero_height = (content_width - dp(44) - tile_width) / 0.96 + extra_height
        top_inset = min(max(h * 0.057, dp(36)), dp(58))
        bottom_inset = max(h * 0.04, dp(28))
        history_height = min(max(h * 0.5, dp(382)), dp(420))

        self._root.padding = [dp(16), top_inset, dp(16), bottom_inset]
        self._root.width = content_width
        self._root.center_x = self.center_x
        self._root.y = self.y
        self._root.height = h

        self._hero.height = hero_height
        self._tiles.width = tile_width
        self.history_panel.height = (
            history_height + dp(ModernHistoryPanel.PANEL_EXTENSION)
        )
        self.history_panel.size_hint_y = None

    # ---- data surface (driven by the screen controller) ---------------------

    def show_loading(self) -> None:
        self.history_panel.show_loading()

    def show_error(self) -> None:
        self.history_panel.show_error()

    def show_payments(self, payments: List[PaymentDetails]) -> None:
        self.history_panel.show_payments(payments)
