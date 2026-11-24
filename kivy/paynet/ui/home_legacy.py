# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/ui/home/LegacyHomeDashboard.kt
# and the PaymentActionButtons / TransactionItem composables it consumes
# from app/src/main/java/com/paynet/app/MainActivity.kt.

"""The pre-existing OG Blue home, preserved separately from the modern
presentation (HomeDashboard.kt selects this variant when the appearance is
classic and not monochrome)."""

import os

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Ellipse, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from paynet import theme
from paynet.db.models import PaymentDetails, PaymentStatus
from paynet.utils.currency import inr
from paynet.utils.dates import format_date
from paynet.ui.home import Glyph, _crop_region, _gradient_texture

STR_TAGLINE = "UPI payments, even offline"
STR_CONNECTED_BANK = "Connected Bank"
STR_SETTINGS = "Settings"
STR_WALLET = "Wallet"
STR_RECENT = "Recent Payments"
STR_RECENT_SUBTITLE = "Your latest transactions"
STR_VIEW_ALL = "View All"
STR_LOADING = "Loading transactions..."
STR_ERROR_TITLE = "Failed to load transactions"
STR_ERROR_UNKNOWN = "Unknown error"
STR_RETRY = "Retry"
STR_EMPTY_TITLE = "No transactions yet"
STR_EMPTY_SUBTITLE = "Your payment history will appear here"
STR_SCAN_QR = "Scan QR Code"
STR_SCAN_OPENING = "Opening…"
STR_SETUP_USSD = "Set up *99#"
STR_PAY_CONTACT = "Pay Contact"
STR_SETUP_UPI123 = "Set up UPI 123 IVR"
STR_OR = "OR"
STR_RECIPIENT_UNKNOWN = "Not recorded"

_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _white(alpha: float):
    return (1, 1, 1, alpha)


def classic_blue_wordmark_size():
    """ClassicBlueWordmark: width is the measured "PayNet" 32sp-bold text
    width; height keeps the 539x123 crop's aspect. Falls back to the
    density-1 measured width when text measurement is unavailable (some
    headless hosts cannot initialise the font cache at build time)."""
    width = None
    try:
        probe = CoreLabel(text="PayNet", font_size="32sp", bold=True)
        probe.refresh()
        if probe.texture and probe.texture.size[0]:
            width = probe.texture.size[0]
    except Exception:
        width = None
    if width is None:
        width = dp(118)
    return width, width * 123.0 / 539.0


class LegacyWordmark(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        path = os.path.join(_ASSETS, "home_wordmark_white_source.png")
        self._region = _crop_region(path, 16, 161, 539, 123) if os.path.exists(path) else None
        self.bind(pos=self._draw, size=self._draw)
        self._draw()

    def _draw(self, *_):
        self.canvas.clear()
        if self._region is not None:
            with self.canvas:
                Rectangle(texture=self._region, pos=self.pos, size=self.size)


class _IconButton(ButtonBehavior, FloatLayout):
    """A filled circle or rounded square with a centered Glyph."""

    def __init__(self, bg, glyph_kind, ink, glyph_scale=0.6, radius=None,
                 gradient=None, on_press=None, **kwargs):
        super().__init__(**kwargs)
        self._bg = bg
        self._gradient = gradient
        self._radius = radius  # None -> circle
        self._glyph_scale = glyph_scale
        self._on_press = on_press
        self.glyph = Glyph(glyph_kind, ink, size_hint=(None, None))
        self.add_widget(self.glyph)
        self.bind(pos=self._draw, size=self._draw)
        self._draw()

    def _draw(self, *_):
        self.canvas.before.clear()
        w, h = self.size
        with self.canvas.before:
            Color(rgba=(1, 1, 1, 1) if self._gradient is not None else self._bg)
            if self._radius is None:
                shape = Ellipse(pos=self.pos, size=(w, h))
            else:
                shape = RoundedRectangle(pos=self.pos, size=(w, h),
                                         radius=[dp(self._radius)])
            if self._gradient is not None:
                shape.texture = self._gradient
        self.glyph.size = (w * self._glyph_scale, h * self._glyph_scale)
        self.glyph.center = self.center

    def on_release(self):
        if self._on_press is not None:
            self._on_press()


class _TextLink(ButtonBehavior, Label):
    def __init__(self, text, on_press=None, **kwargs):
        kwargs.setdefault("halign", "right")
        kwargs.setdefault("valign", "middle")
        super().__init__(text=text, **kwargs)
        self._on_press = on_press
        self.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))

    def on_release(self):
        if self._on_press is not None:
            self._on_press()


def _left_label(text, size, color, bold=False):
    lab = Label(text=text, font_size=size, bold=bold, color=color,
                halign="left", valign="middle")
    lab.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
    return lab


class LegacyHeaderCard(FloatLayout):
    """The 220dp gradient header: wordmark + tagline, settings circle,
    bank box with wallet glyph."""

    HEIGHT = 220

    def __init__(self, bank_name: str, palette, on_settings, **kwargs):
        super().__init__(**kwargs)
        start, end = palette.header_gradient_start, palette.header_gradient_end

        self._card = FloatLayout(size_hint=(None, None))
        self.add_widget(self._card)
        with self._card.canvas.before:
            Color(rgba=(1, 1, 1, 1))
            self._card_bg = RoundedRectangle(radius=[dp(20)])
        self._card_bg.texture = _gradient_texture(start, end)
        self.bind(pos=self._layout, size=self._layout)

        inner = BoxLayout(orientation="vertical",
                          padding=[dp(20), dp(28), dp(20), dp(20)], spacing=dp(20))
        self._card.add_widget(inner)

        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(64))
        brand = BoxLayout(orientation="vertical", spacing=0)
        wm_w, wm_h = classic_blue_wordmark_size()
        brand.add_widget(LegacyWordmark(size_hint=(None, None), size=(wm_w, wm_h)))
        brand.add_widget(_left_label(STR_TAGLINE, "15sp", _white(0.95)))
        top.add_widget(brand)
        settings_anchor = AnchorLayout(anchor_x="right", anchor_y="top",
                                       size_hint_x=None, width=dp(44),
                                       padding=[0, dp(8), dp(8), 0])
        settings_anchor.add_widget(_IconButton(
            _white(0.22), "gear", (1, 1, 1, 1), glyph_scale=0.67,
            on_press=on_settings,
            size_hint=(None, None), size=(dp(36), dp(36))))
        top.add_widget(settings_anchor)
        inner.add_widget(top)

        bank_box = BoxLayout(orientation="horizontal", size_hint_y=None,
                             height=dp(80), padding=[dp(18), dp(14)], spacing=dp(12))
        with bank_box.canvas.before:
            Color(rgba=end)
            bank_box._bg = RoundedRectangle(radius=[dp(16)])
        bank_box.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                      size=lambda w, _: setattr(w._bg, "size", w.size))
        labels = BoxLayout(orientation="vertical", spacing=dp(6))
        labels.add_widget(_left_label(STR_CONNECTED_BANK, "12sp", _white(0.85)))
        labels.add_widget(_left_label(bank_name, "18sp", (1, 1, 1, 1), bold=True))
        bank_box.add_widget(labels)
        bank_box.add_widget(_IconButton(
            _white(0.22), "wallet", (1, 1, 1, 1), glyph_scale=0.54,
            size_hint=(None, None), size=(dp(48), dp(48))))
        inner.add_widget(bank_box)
        self._layout()

    def _layout(self, *_):
        self._card.pos = (self.x + dp(16), self.y)
        self._card.size = (max(self.width - dp(32), 0), self.height)
        self._card_bg.pos = self._card.pos
        self._card_bg.size = self._card.size
        self._card.children[0].pos = self._card.pos
        self._card.children[0].size = self._card.size


class LegacyScanButton(BoxLayout):
    """ScanQrButton: 70dp gradient (or dim) circle + state label."""

    def __init__(self, palette, is_ussd_ready, is_scanning, on_scan, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(10), **kwargs)
        self._on_scan = on_scan
        self.is_ussd_ready = is_ussd_ready
        self.is_scanning = is_scanning

        if is_ussd_ready:
            bg = None
            gradient = _gradient_texture(palette.header_gradient_start,
                                         palette.header_gradient_end)
            kind, ink = "qr", (1, 1, 1, 1)
        else:
            bg = theme.SURFACE_DIM
            gradient = None
            kind, ink = "lock", _white(0.5)
        circle = _IconButton(bg, kind, ink, glyph_scale=0.46, gradient=gradient,
                             on_press=self._press,
                             size_hint=(None, None), size=(dp(70), dp(70)))
        anchor = AnchorLayout(anchor_x="center", size_hint_y=None, height=dp(70))
        anchor.add_widget(circle)
        self.add_widget(anchor)

        self.add_widget(Label(
            text=self._text(), font_size="15sp", bold=True,
            color=(1, 1, 1, 1) if is_ussd_ready else theme.TEXT_LIGHT_GRAY,
            size_hint_y=None, height=dp(22)))

    def _text(self):
        if not self.is_ussd_ready:
            return STR_SETUP_USSD
        return STR_SCAN_OPENING if self.is_scanning else STR_SCAN_QR

    def _press(self):
        # detectTapGestures: taps are swallowed while a scan is opening.
        if not self.is_scanning and self._on_scan is not None:
            self._on_scan()


class LegacyPayButton(BoxLayout):
    """PayContactButton: 70dp rounded-20 gradient (or dim) square + label."""

    def __init__(self, palette, is_upi123_ready, on_pay_contact, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(10), **kwargs)
        self._on_pay = on_pay_contact

        if is_upi123_ready:
            bg = None
            gradient = _gradient_texture(palette.header_gradient_start,
                                         palette.header_gradient_end)
            kind, ink = "person", (1, 1, 1, 1)
        else:
            bg = theme.MEDIUM_GRAY
            gradient = None
            kind, ink = "lock", _white(0.5)
        square = _IconButton(bg, kind, ink, glyph_scale=0.46, gradient=gradient,
                             radius=20, on_press=self._press,
                             size_hint=(None, None), size=(dp(70), dp(70)))
        anchor = AnchorLayout(anchor_x="center", size_hint_y=None, height=dp(70))
        anchor.add_widget(square)
        self.add_widget(anchor)

        self.add_widget(Label(
            text=STR_PAY_CONTACT if is_upi123_ready else STR_SETUP_UPI123,
            font_size="15sp", bold=True,
            color=(1, 1, 1, 1) if is_upi123_ready else theme.TEXT_LIGHT_GRAY,
            size_hint_y=None, height=dp(22)))

    def _press(self):
        if self._on_pay is not None:
            self._on_pay()


class LegacyActionButtons(BoxLayout):
    """PaymentActionButtons: scan circle, OR divider, pay square."""

    HEIGHT = 268

    def __init__(self, palette, is_upi123_ready, is_ussd_ready, is_scanning,
                 on_scan, on_pay_contact, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(20),
                         padding=[dp(32), 0], **kwargs)
        self.scan = LegacyScanButton(palette, is_ussd_ready, is_scanning, on_scan,
                                     size_hint_y=None, height=dp(102))
        self.add_widget(self.scan)

        divider = BoxLayout(orientation="horizontal", spacing=dp(12),
                            size_hint_y=None, height=dp(24))
        line_l = self._divider_line()
        line_r = self._divider_line()
        pill_anchor = AnchorLayout(size_hint_x=None, width=dp(40))
        pill = Label(text=STR_OR, font_size="12sp", color=_white(0.8),
                     size_hint=(None, None), size=(dp(34), dp(18)))
        with pill.canvas.before:
            Color(rgba=_white(0.1))
            pill._pill = Ellipse(pos=pill.pos, size=pill.size)
        pill.bind(pos=lambda w, _: setattr(w._pill, "pos", w.pos),
                  size=lambda w, _: setattr(w._pill, "size", w.size))
        pill_anchor.add_widget(pill)
        divider.add_widget(line_l)
        divider.add_widget(pill_anchor)
        divider.add_widget(line_r)
        self.add_widget(divider)

        self.pay = LegacyPayButton(palette, is_upi123_ready, on_pay_contact,
                                   size_hint_y=None, height=dp(102))
        self.add_widget(self.pay)

    def _divider_line(self):
        line = Widget(size_hint_x=None, width=dp(50))
        with line.canvas:
            Color(rgba=_white(0.3))
            line._rect = Rectangle(size=(dp(50), dp(1)))
        line.bind(pos=self._line_pos)
        return line

    @staticmethod
    def _line_pos(w, *_):
        w._rect.pos = (w.x, w.center_y)


class LegacyTransactionItem(ButtonBehavior, FloatLayout):
    """TransactionItem: 90dp SurfaceDim card, recipient + date, outcome."""

    HEIGHT = 90

    def __init__(self, payment: PaymentDetails, palette, on_press=None, **kwargs):
        super().__init__(**kwargs)
        self._on_press = on_press
        self._payment = payment
        with self.canvas.before:
            Color(rgba=theme.SURFACE_DIM)
            self._bg = RoundedRectangle(radius=[dp(16)])
        self.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))

        row = BoxLayout(orientation="horizontal", padding=[dp(18), dp(14)],
                        spacing=dp(12))
        self.add_widget(row)

        labels = BoxLayout(orientation="vertical", spacing=dp(8))
        labels.add_widget(_left_label(payment.recipient_label or STR_RECIPIENT_UNKNOWN,
                                      "16sp", (1, 1, 1, 1), bold=True))
        labels.add_widget(_left_label(format_date(payment.timestamp), "14sp",
                                      theme.TEXT_PALE))
        row.add_widget(labels)

        start = palette.header_gradient_start
        if payment.userConfirmed is not None:
            kind = "check" if payment.userConfirmed else "close"
            row.add_widget(Glyph(kind, start, size_hint=(None, None),
                                 size=(dp(24), dp(24))))
        elif payment.amountRecorded:
            failed = payment.status in (PaymentStatus.FAILED, PaymentStatus.CANCELLED)
            outcome = BoxLayout(orientation="horizontal", spacing=dp(8),
                                size_hint_x=None, width=dp(150))
            outcome.add_widget(_left_label("₹" + inr(payment.amount), "16sp",
                                           start, bold=True))
            outcome.children[0].halign = "right"
            outcome.add_widget(Glyph("close" if failed else "arrow",
                                     theme.STATUS_ERROR if failed else start,
                                     size_hint=(None, None), size=(dp(18), dp(18))))
            row.add_widget(outcome)

    def on_release(self):
        if self._on_press is not None:
            self._on_press(self._payment)


class LegacyHistoryCard(FloatLayout):
    """The recent-transactions card: header, then loading / error / empty /
    the 372dp list of LegacyTransactionItem rows."""

    LIST_HEIGHT = 372

    def __init__(self, palette, on_history=None, on_retry=None, on_transaction=None,
                 **kwargs):
        super().__init__(**kwargs)
        self._palette = palette
        self._on_history = on_history
        self._on_retry = on_retry
        self._on_transaction = on_transaction
        with self.canvas.before:
            Color(rgba=theme.SURFACE_DIM)
            self._bg = RoundedRectangle(radius=[dp(20)])
        self.bind(pos=self._layout, size=self._layout)

        self._content = BoxLayout(orientation="vertical", padding=[dp(20), dp(20)],
                                  spacing=dp(20), size_hint=(None, None))
        self.add_widget(self._content)

        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40))
        icon_holder = AnchorLayout(size_hint=(None, None), size=(dp(40), dp(40)))
        icon_holder.add_widget(Glyph("history", palette.header_gradient_start,
                                     size_hint=(None, None), size=(dp(20), dp(20))))
        header.add_widget(icon_holder)
        header.add_widget(Widget(size_hint_x=None, width=dp(12)))
        titles = BoxLayout(orientation="vertical")
        titles.add_widget(_left_label(STR_RECENT, "18sp", (1, 1, 1, 1), bold=True))
        titles.add_widget(_left_label(STR_RECENT_SUBTITLE, "12sp", theme.TEXT_LIGHT_GRAY))
        header.add_widget(titles)
        header.add_widget(_TextLink(STR_VIEW_ALL, on_history, font_size="12sp",
                                    color=palette.accent,
                                    size_hint_x=None, width=dp(56)))
        self._content.add_widget(header)

        # DEVIATION: Kotlin gives this list its own LazyColumn scroll inside
        # the screen's outer verticalScroll. Kivy nested ScrollViews do not
        # compose reliably (the inner viewport's canvas translation is not
        # applied), so the card shows the first rows that fit and the rest
        # live behind View All (feature 9's full history screen).
        # DEVIATION: manual geometry instead of LazyColumn's scroll — Kivy
        # ScrollView viewport translation proved unreliable in this build.
        # The full list lives behind View All (feature 9).
        # Fully manual list geometry: no BoxLayout stacking, no ScrollView.
        # Items are positioned in _layout_states/show_payments from the
        # body's own rect.
        self._body = FloatLayout(size_hint_y=None, height=dp(self.LIST_HEIGHT))
        self._body.bind(pos=self._reposition, size=self._reposition)
        self._content.add_widget(self._body)
        self._layout()

    def _layout(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._content.pos = self.pos
        self._content.size = self.size
        self._reposition()

    def _reposition(self, *_):
        for i, child in enumerate(reversed(self._body.children)):
            child.x = self._body.x
            child.width = self._body.width
            child.top = self._body.top - i * (child.height + dp(10))



    # -- states --------------------------------------------------------------

    def _center_state(self):
        self._body.clear_widgets()
        col = BoxLayout(orientation="vertical", spacing=dp(6),
                        size_hint=(None, None), height=dp(288),
                        padding=[0, dp(40), 0, 0])
        self._body.add_widget(col)
        self._reposition()
        return col

    def show_loading(self):
        col = self._center_state()
        col.add_widget(Label(text="…", font_size="28sp",
                             color=self._palette.header_gradient_start,
                             size_hint_y=None, height=dp(52)))
        col.add_widget(Label(text=STR_LOADING, font_size="14sp",
                             color=theme.TEXT_LIGHT_GRAY, size_hint_y=None,
                             height=dp(24)))

    def show_error(self, error=None):
        col = self._center_state()
        col.add_widget(Label(text=STR_ERROR_TITLE, font_size="16sp", bold=True,
                             color=(1, 1, 1, 1), size_hint_y=None, height=dp(26)))
        col.add_widget(Label(text=error or STR_ERROR_UNKNOWN, font_size="13sp",
                             color=theme.TEXT_LIGHT_GRAY, size_hint_y=None,
                             height=dp(22)))
        retry_anchor = AnchorLayout(anchor_x="center", size_hint_y=None, height=dp(40))
        retry_anchor.add_widget(_TextLink(
            STR_RETRY, self._on_retry, font_size="14sp", bold=True,
            color=self._palette.header_gradient_start,
            size_hint=(None, None), size=(dp(60), dp(40)), halign="center"))
        col.add_widget(retry_anchor)

    def show_payments(self, payments):
        self._body.clear_widgets()
        if not payments:
            col = self._center_state()
            holder = AnchorLayout(size_hint_y=None, height=dp(64))
            circle = Widget(size_hint=(None, None), size=(dp(64), dp(64)))
            with circle.canvas.before:
                Color(rgba=theme.MEDIUM_GRAY)
                circle._bg = Ellipse(pos=circle.pos, size=circle.size)
            circle.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                        size=lambda w, _: setattr(w._bg, "size", w.size))
            circle.add_widget(Glyph("history", theme.TEXT_LIGHT_GRAY,
                                    size_hint=(None, None), size=(dp(32), dp(32))))
            circle.children[0].center = circle.center
            circle.bind(center=lambda w, _: setattr(w.children[0], "center", w.center))
            holder.add_widget(circle)
            col.add_widget(holder)
            col.add_widget(Label(text=STR_EMPTY_TITLE, font_size="16sp", bold=True,
                                 color=(1, 1, 1, 1), size_hint_y=None, height=dp(40)))
            col.add_widget(Label(text=STR_EMPTY_SUBTITLE, font_size="13sp",
                                 color=theme.TEXT_LIGHT_GRAY, size_hint_y=None,
                                 height=dp(22)))
            return
        # The 372dp viewport fits three 90dp rows plus spacing; the rest
        # live behind View All.
        for payment in payments[:3]:
            item = LegacyTransactionItem(
                payment, self._palette, on_press=self._on_transaction,
                # FloatLayout skips hint-free children; with a hint it would
                # reset our manual position on every layout pass.
                size_hint=(None, None), height=dp(LegacyTransactionItem.HEIGHT))
            self._body.add_widget(item)
        self._reposition()


class LegacyHomeScreen(FloatLayout):
    """LegacyHomeDashboard: black canvas, centered 420dp-max column with
    header card, action buttons and the history card. (The Compose version
    wraps the column in verticalScroll; all content fits the supported
    viewport range, so the column lays out directly.)"""

    MAX_CONTENT_WIDTH = 420

    def __init__(
        self,
        bank_name: str = "HDFC Bank",
        monochrome: bool = False,
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
        self.is_upi123_ready = is_upi123_ready
        self.is_ussd_ready = is_ussd_ready
        self.is_scanning = is_scanning
        self._on_scan = on_scan
        self._on_pay_contact = on_pay_contact
        palette = theme.accent_theme_for(monochrome)
        self._palette = palette

        with self.canvas.before:
            Color(rgba=(0, 0, 0, 1))
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda *_: setattr(self._bg_rect, "pos", self.pos),
                  size=lambda *_: setattr(self._bg_rect, "size", self.size))

        # DEVIATION: no outer verticalScroll. Nested Kivy ScrollViews do not
        # compose (the outer matrix breaks the inner viewport translation),
        # and the inner list scroll matters more: on short viewports the
        # bottom of the history card is cut off instead of scrollable.
        self._column = BoxLayout(orientation="vertical", spacing=0,
                                 size_hint=(None, None))
        self._column.bind(minimum_height=self._column.setter("height"))
        self.add_widget(self._column)

        def spacer(height):
            return Widget(size_hint_y=None, height=dp(height))

        self.header = LegacyHeaderCard(
            bank_name, palette, on_settings or (lambda: None),
            size_hint_y=None, height=dp(LegacyHeaderCard.HEIGHT))
        self.actions = LegacyActionButtons(
            palette, is_upi123_ready, is_ussd_ready, is_scanning,
            on_scan, on_pay_contact,
            size_hint_y=None, height=dp(LegacyActionButtons.HEIGHT))
        self.history = LegacyHistoryCard(
            palette, on_history=on_history, on_retry=on_retry,
            on_transaction=on_transaction,
            size_hint_y=None, height=dp(452))

        self._column.add_widget(spacer(24))
        self._column.add_widget(self.header)
        self._column.add_widget(spacer(24))
        self._column.add_widget(self.actions)
        self._column.add_widget(spacer(20))
        self._column.add_widget(self.history)
        self._column.add_widget(spacer(24))

        self.bind(size=self._relayout, pos=self._relayout)
        self._relayout()

    def _relayout(self, *_):
        w, h = self.size
        if w <= 0 or h <= 0:
            return
        self._column.width = min(w, dp(self.MAX_CONTENT_WIDTH))
        self._column.center_x = self.center_x
        # Top-align: bottom-anchored overflow would clip the header card.
        self._column.y = self.top - self._column.height

    def update_readiness(self, is_upi123_ready, is_ussd_ready, is_scanning):
        """ON_RESUME re-read: Kotlin recomposes the action buttons; we
        rebuild the actions block in place."""
        self.is_upi123_ready = is_upi123_ready
        self.is_ussd_ready = is_ussd_ready
        self.is_scanning = is_scanning
        order = list(reversed(self._column.children))
        idx = order.index(self.actions)
        self._column.remove_widget(self.actions)
        self.actions = LegacyActionButtons(
            self._palette, is_upi123_ready, is_ussd_ready, is_scanning,
            self._on_scan, self._on_pay_contact,
            size_hint_y=None, height=dp(LegacyActionButtons.HEIGHT))
        self._column.add_widget(self.actions,
                                index=len(self._column.children) - idx)

    # -- data surface --------------------------------------------------------

    def show_loading(self):
        self.history.show_loading()

    def show_error(self, error=None):
        self.history.show_error(error)

    def show_payments(self, payments):
        self.history.show_payments(payments)
