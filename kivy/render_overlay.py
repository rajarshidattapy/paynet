# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Headless render harness for feature 15 (call overlay).
# Usage: xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 python3 render_overlay.py STATE

import os
import sys

os.environ.setdefault("KIVY_NO_ARGS", "1")
from kivy.config import Config

Config.set("graphics", "width", "412")
Config.set("graphics", "height", "892")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle

from paynet.overlay.view import (AUTH_NOTICE, SENDING_REQUEST,
                                 CallOverlayView)

STATE = sys.argv[1] if len(sys.argv) > 1 else "connecting"


class Harness(App):
    def build(self):
        from kivy.uix.floatlayout import FloatLayout
        root = FloatLayout()
        with root.canvas.before:
            # The dialer behind the overlay, darkened for the shot.
            Color(0.12, 0.12, 0.16, 1)
            root._bg = RoundedRectangle(pos=root.pos, size=root.size, radius=[0])
        root.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        view = CallOverlayView(on_terminate=lambda: print("TERMINATE"))
        view.bind_details("+919876543210", "1500")
        if STATE == "in_call":
            view.update_status("Processing Payment", SENDING_REQUEST)
            view.show_progress(450)
        elif STATE == "muted":
            view.update_status("Processing Payment", SENDING_REQUEST)
            view.show_progress(700)
            view.show_muted_indicator()
        elif STATE == "guidance":
            view.update_status("Processing Payment", AUTH_NOTICE)
            view.show_progress(880)
        root.add_widget(view)
        return root


app = Harness()
Clock.schedule_once(lambda *_: (
    print("SHOT", STATE, repr(Window.screenshot(f"/downloads/overlay-{STATE}.png"))),
    app.stop()), 0.9)
app.run()
