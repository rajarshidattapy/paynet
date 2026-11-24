# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Headless render harness for feature 12 (setup + onboarding screens).
# Usage: xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 python3 render_setup_onboarding.py STATE

import os
import sys
import tempfile

os.environ.setdefault("KIVY_NO_ARGS", "1")
from kivy.config import Config

Config.set("graphics", "width", "412")
Config.set("graphics", "height", "892")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window

from paynet.db.settings import PrefsStore, TestResultsManager
from paynet.setup import SetupHelper
from paynet.ui.appearance import AppearanceScreen
from paynet.ui.setup import SetupScreen

STATE = sys.argv[1] if len(sys.argv) > 1 else "setup_empty"


class Harness(App):
    def build(self):
        data_dir = tempfile.mkdtemp(prefix="paynet-render-")
        prefs = PrefsStore(data_dir, "PayNetPrefs")
        results = TestResultsManager(data_dir)
        helper = SetupHelper(prefs, results,
                             show_toast=lambda m: print("TOAST", m),
                             navigate_to_test_configuration=lambda: print("NAVIGATE"))
        if STATE.startswith("setup"):
            screen = SetupScreen(helper, prefs)
            if STATE == "setup_filled":
                screen._bank_row._pick("sbi")
                screen._sim_row._pick("airtel")
                screen._on_disclaimer(True)
            elif STATE == "setup_disclaimer":
                screen._toggle_disclaimer_copy()
            return screen
        if STATE == "appearance_welcome":
            prefs.put("appearance_setup_completed", True)
            return AppearanceScreen(prefs, on_open_home=lambda: print("HOME"),
                                    animations_enabled=False)
        return AppearanceScreen(prefs, on_open_home=lambda: print("HOME"))


app = Harness()
Clock.schedule_once(lambda *_: (
    print("SHOT", STATE, repr(Window.screenshot(f"/downloads/onboarding-{STATE}.png"))),
    app.stop()), 0.9)
app.run()
