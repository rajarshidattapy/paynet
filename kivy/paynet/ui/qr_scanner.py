# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay

"""QR scanner screen — Kivy port of
features/qr_scanner/presentation/QRScannerActivity.kt's view layer
(res/layout/activity_qr_scanner.xml) and its UI hooks.

The camera preview, torch, photo picker and USSD dial are device-only
(feature 17 binds them via pyjnius); the preview area is the scanner scrim
over black here. All payment-flow decisions live in
paynet.qr.scanner.QRScannerController; this screen only renders the states
the controller asks for.

Layout deviations (recorded in MIGRATION.md): the circular ProgressBar is
an ellipsis label, the instructions-card expand is a delayed swap instead
of a cross-fade, glyphs stand in for the vector icons, and the hidden
scan-line view (already `gone` in the XML) is not drawn.
"""

from kivy.clock import Clock
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.graphics import Ellipse
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import ButtonBehavior
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from paynet.qr import scanner as qr
from paynet.qr.scanner import QRScannerController
from paynet.ui.home import Glyph

SCANNER_SCRIM = (0, 0, 0, 0.25)          # #40000000
BUTTON_BG = (0x1C / 255, 0x1C / 255, 0x1C / 255, 0.8)   # #CC1C1C1C
BUTTON_STROKE = (1, 1, 1, 0x1A / 255)    # #1AFFFFFF
FLASH_ACTIVE = (0x4A / 255, 0x90 / 255, 0xE2 / 255, 1)  # #FF4A90E2
FLASH_ACTIVE_STROKE = (1, 1, 1, 0x33 / 255)
BANNER_BG = (0xE6 / 255, 0x17 / 255, 0x17 / 255, 0x19 / 255)  # #E6171719
TERMINATE_BG = (0xBC / 255, 0x33 / 255, 0x45 / 255, 1)  # #BC3345
CARD_BG = (0xF5 / 255, 0xF5 / 255, 0xF5 / 255, 1)  # instructions gradient center
CARD_TEXT = (0, 0, 0, 1)
STEP_TEXT = (0x2E / 255, 0x2B / 255, 0x3D / 255, 1)  # divider_dark
WHITE = (1, 1, 1, 1)
ERROR_RED = (1, 0x44 / 255, 0x44 / 255, 1)  # holo_red_light

STR_STEPS_TITLE = "Follow These Steps"
STR_STEPS = [
    "1. Paste the VPA from clipboard",
    "2. Enter the amount",
    "3. Press one to skip",
    "4. Enter your pin",
    "5. Press cancel to end session",
]

FRAME_DP = 260
CORNER_DP = 64
_CORNER_SCALE = CORNER_DP / 72.0
CHROME_GAP_DP = 20
BOTTOM_BAR_GAP_DP = 48
DISABLED_ALPHA = 0.5


def _corner_points():
    """One rounded bracket from qr_corner.xml (M6,64 V34 C6,18.536 18.536,6
    34,6 H64), y flipped for Kivy's bottom-left origin, in dp."""
    s = _CORNER_SCALE

    def pt(x, y):
        return (dp(x * s), dp((72 - y) * s))

    points = [pt(6, 64), pt(6, 34)]
    # Cubic (6,34) -> (34,6), controls (6,18.536) and (18.536,6).
    p0, c1, c2, p1 = (6, 34), (6, 18.536), (18.536, 6), (34, 6)
    for i in range(1, 9):
        t = i / 8
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt * mt * t * c1[0] \
            + 3 * mt * t * t * c2[0] + t**3 * p1[0]
        y = mt**3 * p0[1] + 3 * mt * mt * t * c1[1] \
            + 3 * mt * t * t * c2[1] + t**3 * p1[1]
        points.append(pt(x, y))
    points.append(pt(64, 6))
    return points


_CORNER = _corner_points()


def _rot(points, quarter_turns):
    """Rotate the bracket around the 64dp box center, 90° CCW per turn."""
    c = dp(CORNER_DP) / 2
    out = points
    for _ in range(quarter_turns % 4):
        out = [(c - (y - c), c + (x - c)) for x, y in out]
    return out


class _CircleButton(ButtonBehavior, FloatLayout):
    """The 48/56/64dp circular icon buttons (torch, gallery, close,
    terminate). Background uses persistent canvas instructions (the
    RoundedBox pattern); the icon is a Glyph child."""

    def __init__(self, diameter_dp, icon, bg, stroke=None,
                 on_press=None, **kwargs):
        super().__init__(size_hint=(None, None),
                         size=(dp(diameter_dp), dp(diameter_dp)), **kwargs)
        self._has_stroke = stroke is not None
        with self.canvas.before:
            # The outline is a ring: a full-size ellipse in the stroke color
            # behind the fill ellipse inset by the stroke width. (A
            # Line(circle=...) stops following position updates — do not
            # use one here.)
            self._stroke_color_instr = Color(rgba=stroke or bg)
            self._ring = Ellipse(pos=self.pos, size=self.size)
            self._fill = Color(rgba=bg)
            self._circle = Ellipse(pos=(self.x + 1, self.y + 1),
                                   size=(self.width - 2, self.height - 2))
        self.bind(pos=self._redraw, size=self._redraw)
        self.add_widget(Glyph(icon, WHITE, size_hint=(1, 1),
                              pos_hint={"x": 0, "y": 0}))
        self._redraw()
        if on_press is not None:
            self.bind(on_release=lambda *_: on_press())

    def set_bg(self, bg, stroke):
        self._fill.rgba = bg
        self._stroke_color_instr.rgba = stroke or bg
        self._redraw()

    def _redraw(self, *_):
        self._ring.pos = self.pos
        self._ring.size = self.size
        inset = 1 if self._has_stroke else 0
        self._circle.pos = (self.x + inset, self.y + inset)
        self._circle.size = (self.width - 2 * inset,
                             self.height - 2 * inset)


class _ScannerFrame(FloatLayout):
    """The 260dp frame with four white rounded corner brackets."""

    def __init__(self, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(FRAME_DP),
                                                       dp(FRAME_DP)), **kwargs)
        self.bind(pos=self._redraw, size=self._redraw)
        self._redraw()

    def _redraw(self, *_):
        self.canvas.before.clear()
        arm = dp(CORNER_DP)
        with self.canvas.before:
            Color(rgba=WHITE)
            # Bracket arms at each corner: top-left, top-right, bottom-right,
            # bottom-left (rotations 0/90/180/270 in the XML).
            placements = [
                (self.x, self.y + self.height - arm, _rot(_CORNER, 0)),
                (self.x + self.width - arm, self.y + self.height - arm,
                 _rot(_CORNER, 3)),
                (self.x + self.width - arm, self.y, _rot(_CORNER, 2)),
                (self.x, self.y, _rot(_CORNER, 1)),
            ]
            for ox, oy, pts in placements:
                flat = []
                for px, py in pts:
                    flat += [ox + px, oy + py]
                Line(points=flat, width=dp(4.67), cap="round", joint="round")


class KivyScheduler:
    """Handler(Looper.getMainLooper()) over Kivy's Clock: keyed postDelayed
    where a newer post replaces an older one."""

    def __init__(self):
        self._events = {}

    def post_delayed(self, key, delay_ms, fn):
        self.cancel(key)
        self._events[key] = Clock.schedule_once(lambda _dt: fn(),
                                                delay_ms / 1000.0)

    def cancel(self, key):
        event = self._events.pop(key, None)
        if event is not None:
            event.cancel()

    def cancel_all(self):
        for event in self._events.values():
            event.cancel()
        self._events.clear()


class QRScannerScreen(Screen):
    def __init__(self, session_manager, detector=None, show_toast=None,
                 on_close=None, dial=None, has_call_permission=lambda: False,
                 request_call_permission=None, blocked_message=lambda: None,
                 clipboard=None, decode_gallery_image=None, **kwargs):
        super().__init__(**kwargs)
        self._on_close = on_close or (lambda result: None)
        self.is_flash_on = False

        self._root = FloatLayout()
        with self._root.canvas.before:
            Color(rgba=(0, 0, 0, 1))
            self._bg = RoundedRectangle(radius=[0], pos=self._root.pos,
                                        size=self._root.size)
            Color(rgba=SCANNER_SCRIM)
            self._scrim = RoundedRectangle(radius=[0], pos=self._root.pos,
                                           size=self._root.size)
        self._root.bind(
            pos=lambda w, _: self._layout_bg(),
            size=lambda w, _: self._layout_bg())
        self.add_widget(self._root)

        # Scanner frame, vertically biased 0.42 from the top.
        self._frame = _ScannerFrame()
        self._root.add_widget(self._frame)
        self._root.bind(size=lambda *_: self._layout_frame())
        self._layout_frame()

        # Top bar: close control at the top-right. The button sits on the
        # root directly — a FloatLayout parent would not translate its pos.
        self._btn_close = _CircleButton(48, "close", BUTTON_BG,
                                        BUTTON_STROKE,
                                        on_press=self._back_pressed)
        self._root.add_widget(self._btn_close)

        # Bottom action bar: torch + gallery.
        self._bottom_bar = BoxLayout(size_hint=(None, None),
                                     size=(dp(64 + 28 + 64), dp(64)),
                                     spacing=dp(28))
        self._btn_flash = _CircleButton(64, "flash", BUTTON_BG,
                                        BUTTON_STROKE,
                                        on_press=self._flash_pressed)
        self._btn_gallery = _CircleButton(64, "gallery", BUTTON_BG,
                                          BUTTON_STROKE,
                                          on_press=self._gallery_pressed)
        self._bottom_bar.add_widget(self._btn_flash)
        self._bottom_bar.add_widget(self._btn_gallery)
        self._root.add_widget(self._bottom_bar)

        # Invalid-scan banner over the live preview.
        self._banner = FloatLayout(size_hint=(None, None))
        with self._banner.canvas.before:
            Color(rgba=BANNER_BG)
            self._banner_bg = RoundedRectangle(radius=[dp(16)])
        self._banner.bind(pos=lambda w, _: setattr(
            self._banner_bg, "pos", w.pos), size=lambda w, _: setattr(
            self._banner_bg, "size", w.size))
        self._banner_title = Label(text=qr.STR_INVALID_TITLE, bold=True,
                                   font_size="15sp", color=WHITE,
                                   size_hint=(1, None), height=dp(20))
        self._banner_body = Label(text="", font_size="14sp", color=WHITE,
                                  size_hint=(1, None), height=dp(20))
        banner_col = BoxLayout(orientation="vertical", spacing=dp(6),
                               padding=(dp(16), dp(16)), size_hint=(1, 1),
                               pos_hint={"x": 0, "y": 0})
        banner_col.add_widget(self._banner_title)
        banner_col.add_widget(self._banner_body)
        self._banner.add_widget(banner_col)
        self._banner.opacity = 0
        self._banner_visible = False
        self._root.add_widget(self._banner)

        # Instructions card (black waiting screen).
        self._instructions = FloatLayout(size_hint=(None, None),
                                         size=(dp(372), dp(190)))
        with self._instructions.canvas.before:
            Color(rgba=CARD_BG)
            self._card_bg = RoundedRectangle(radius=[dp(20)])
        self._instructions.bind(pos=lambda w, _: setattr(
            self._card_bg, "pos", w.pos), size=lambda w, _: setattr(
            self._card_bg, "size", w.size))
        self._steps_title = Label(text=STR_STEPS_TITLE, bold=True,
                                  font_size="32sp", color=CARD_TEXT,
                                  size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
        self._steps = BoxLayout(orientation="vertical", size_hint=(1, 1),
                                pos_hint={"x": 0, "y": 0},
                                padding=(dp(24), dp(22)), spacing=dp(10))
        for step in STR_STEPS:
            label = Label(text=step, font_size="15sp", color=STEP_TEXT,
                          halign="left", valign="middle",
                          size_hint_y=None, height=dp(24))
            label.bind(size=lambda w, s: setattr(w, "text_size", s))
            self._steps.add_widget(label)
        self._steps.opacity = 0
        self._instructions.add_widget(self._steps_title)
        self._instructions.add_widget(self._steps)
        self._instructions.opacity = 0
        self._instructions_visible = False
        self._root.add_widget(self._instructions)

        # Status text under the instructions card.
        self._status = Label(text="", font_size="16sp", color=WHITE,
                             halign="center", valign="middle")
        self._status.bind(size=lambda w, s: setattr(w, "text_size", s))
        self._status.opacity = 0
        self._root.add_widget(self._status)

        # Progress (ellipsis stands in for the circular ProgressBar).
        self._progress = Label(text="…", font_size="40sp", color=WHITE)
        self._progress.opacity = 0
        self._root.add_widget(self._progress)

        # Terminate button.
        self._btn_terminate = _CircleButton(
            56, "close", TERMINATE_BG, None,
            on_press=self._terminate_pressed)
        self._btn_terminate.opacity = 0
        self._btn_terminate.disabled = True
        self._root.add_widget(self._btn_terminate)

        self._scheduler = KivyScheduler()
        self.controller = QRScannerController(
            self, session_manager, detector=detector, clipboard=clipboard,
            show_toast=show_toast, dial=dial,
            has_call_permission=has_call_permission,
            request_call_permission=request_call_permission,
            scheduler=self._scheduler, on_finish=self._on_close,
            blocked_message=blocked_message,
            decode_gallery_image=decode_gallery_image)
        self.controller.on_created()

        self._root.bind(size=lambda *_: self._layout_chrome())
        Clock.schedule_once(lambda *_: self._layout_chrome(), 0)

    # ---- layout ---------------------------------------------------------------

    def _layout_bg(self):
        self._bg.pos = self._root.pos
        self._bg.size = self._root.size
        self._scrim.pos = self._root.pos
        self._scrim.size = self._root.size

    def _layout_frame(self):
        w, h = self._root.size
        if h <= 0:
            return
        self._frame.center_x = self._root.x + w / 2
        # ConstraintLayout vertical bias 0.42 between top and bottom.
        self._frame.y = self._root.y + (h - self._frame.height) * (1 - 0.42)

    def _layout_chrome(self):
        w, h = self._root.size
        x = self._root.x
        top = self._root.y + h
        self._btn_close.right = x + w - dp(20)
        self._btn_close.y = top - dp(CHROME_GAP_DP) - dp(48)
        self._bottom_bar.center_x = x + w / 2
        self._bottom_bar.y = self._root.y + dp(BOTTOM_BAR_GAP_DP)
        self._banner.width = w - dp(48)
        self._banner.height = dp(20 + 20 + 6 + 32)
        self._banner.center_x = x + w / 2
        self._banner.y = (self._bottom_bar.top + dp(24))
        self._instructions.size = (w - dp(40), dp(190))
        self._instructions.pos = (
            x + dp(20), top - dp(20 + CHROME_GAP_DP) - dp(190))
        # Sync the card background directly: when the computed size equals
        # the constructor's, the bind never fires and the bg stays 100x100.
        self._card_bg.pos = self._instructions.pos
        self._card_bg.size = self._instructions.size
        self._banner_bg.pos = self._banner.pos
        self._banner_bg.size = self._banner.size
        self._status.size = (w - dp(64), dp(60))
        self._status.pos = (x + dp(32),
                            self._instructions.y - dp(32) - dp(60))
        self._progress.center = self._root.center
        self._btn_terminate.center_x = x + w / 2
        self._btn_terminate.y = self._root.y + dp(56)

    # ---- button handlers --------------------------------------------------------

    def _back_pressed(self):
        self.controller.back()

    def _terminate_pressed(self):
        self.controller.terminate()

    def _flash_pressed(self):
        # The torch is device-only; the toggle and its visuals are ported,
        # the cameraControl.enableTorch call is feature 17.
        self.is_flash_on = not self.is_flash_on
        if self.is_flash_on:
            self._btn_flash.set_bg(FLASH_ACTIVE, FLASH_ACTIVE_STROKE)
        else:
            self._btn_flash.set_bg(BUTTON_BG, BUTTON_STROKE)

    def _gallery_pressed(self):
        # The photo picker is device-only; on Android this opens the system
        # picker and its result re-enters via on_gallery_picked.
        self.controller.open_gallery_picker(lambda: None)

    # ---- controller ui hooks ------------------------------------------------------

    def show_processing(self, text):
        self._frame.opacity = 0
        self._bottom_bar.opacity = 0
        self._show_widget(self._progress, True)
        self._status.text = text
        self._status.color = WHITE
        self._show_widget(self._status, True)

    def show_invalid_banner(self, message):
        title, _, body = message.partition("\n")
        self._banner_title.text = title
        self._banner_body.text = body
        self._frame.opacity = 1
        self._bottom_bar.opacity = 1
        self._btn_close.opacity = 1
        self._btn_close.disabled = False
        self._show_widget(self._progress, False)
        self._show_widget(self._status, False)
        self._show_widget(self._banner, True)

    def hide_invalid_banner(self):
        self._show_widget(self._banner, False)

    def show_black_screen(self, status_text):
        self.controller.qr_guide_visible = True
        self._frame.opacity = 0
        self._bottom_bar.opacity = 0
        self._btn_close.opacity = 0
        self._btn_close.disabled = True
        self._show_widget(self._progress, False)
        # Instructions box in its initial state.
        self._show_widget(self._instructions, True)
        self._steps_title.opacity = 1
        self._steps.opacity = 0
        self._status.text = status_text
        self._status.color = WHITE
        self._show_widget(self._status, True)
        self._show_widget(self._btn_terminate, True)
        self._btn_terminate.disabled = False
        # Expand the instructions into the step list after 4 seconds (a
        # delayed swap instead of the cross-fade).
        self._scheduler.post_delayed(
            "expand_instructions", qr.INSTRUCTIONS_EXPAND_DELAY_MS,
            self._expand_instructions)

    def _expand_instructions(self):
        if not self._instructions_visible:
            return
        self._steps_title.opacity = 0
        self._steps.opacity = 1

    def update_status(self, text, error=False):
        self._status.text = text
        if error:
            self._status.color = ERROR_RED

    def show_sms_waiting_state(self, text):
        # The outcome panel is dead code in the Kotlin (only ever hidden),
        # so this is just the status update.
        self.update_status(text)

    def show_error_status(self, text):
        self.update_status(text, error=True)

    def reset_to_camera_view(self):
        self._show_widget(self._instructions, False)
        self._steps_title.opacity = 1
        self._steps.opacity = 0
        self._show_widget(self._btn_terminate, False)
        self._btn_terminate.disabled = True
        self._show_widget(self._status, False)
        self._show_widget(self._progress, False)
        self._frame.opacity = 1
        self._bottom_bar.opacity = 1
        self._btn_close.opacity = 1
        self._btn_close.disabled = False
        self.is_flash_on = False
        self._btn_flash.set_bg(BUTTON_BG, BUTTON_STROKE)
        self.resume_live_scanning()

    def show_gallery_reading(self, text):
        self._show_widget(self._banner, False)
        self._frame.opacity = 0
        self._show_widget(self._progress, True)
        self._status.text = text
        self._status.color = WHITE
        self._show_widget(self._status, True)

    def finish_gallery_selection(self):
        self._show_widget(self._progress, False)
        self._show_widget(self._status, False)
        self._frame.opacity = 1
        self.resume_live_scanning()

    def set_controls_enabled(self, enabled):
        for control in (self._btn_gallery, self._btn_flash):
            control.disabled = not enabled
            control.opacity = 1 if enabled else DISABLED_ALPHA

    def stop_live_analysis(self):
        # Camera pipeline is device-only.
        pass

    def resume_live_scanning(self):
        # Camera pipeline is device-only.
        pass

    def rearm_scanning(self):
        # Invalid codes reuse the analyzer, preserving its duplicate
        # cooldown; the analyzer lives in the device camera pipeline.
        pass

    # ---- helpers ------------------------------------------------------------------

    def _show_widget(self, widget, show):
        widget.opacity = 1 if show else 0
        if widget is self._instructions:
            self._instructions_visible = show
        if widget is self._banner:
            self._banner_visible = show
        widget.disabled = not show
