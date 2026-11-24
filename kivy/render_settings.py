# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Headless render harness for feature 13 (settings screen).
# Usage: xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 python3 render_settings.py STATE

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

from paynet.db.database import Database
from paynet.db.settings import PrefsStore, SettingsRepository, TestResultsManager
from paynet.repository import TransactionRepository
from paynet.ui.settings import SettingsScreen

STATE = sys.argv[1] if len(sys.argv) > 1 else "main"


class Harness(App):
    def build(self):
        data_dir = tempfile.mkdtemp(prefix="paynet-render-")
        prefs = PrefsStore(data_dir, "PayNetPrefs")
        prefs.put("selected_bank", "sbi")
        prefs.put("selected_primary_sim", "airtel")
        screen = SettingsScreen(
            prefs, SettingsRepository(data_dir), TestResultsManager(data_dir),
            TransactionRepository(Database(os.path.join(data_dir, "paynet.db"))),
            on_back=lambda: print("BACK"),
            on_open_setup=lambda: print("SETUP"),
            permission_provider=lambda: {"phone": True, "camera": False,
                                         "contacts": False, "overlay": False})
        if STATE != "main":
            screen._open_sheet(STATE)
        return screen


app = Harness()
Clock.schedule_once(lambda *_: (
    print("SHOT", STATE, repr(Window.screenshot(f"/downloads/settings-{STATE}.png"))),
    app.stop()), 0.9)
app.run()
