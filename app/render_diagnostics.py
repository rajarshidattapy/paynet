# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Headless render harness for feature 16 (test-configuration screen +
# install-count consent screen).
# Usage: xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 python3 render_diagnostics.py STATE

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

from paynet.db.settings import PrefsStore, TestResults, TestResultsManager
from paynet.metrics import InstallCountScreen, InstallReporter
from paynet.permissions import PermissionManager
from paynet.telephony.call_manager import CallType
from paynet.ui.diagnostics import TestConfigurationHelper, TestConfigurationScreen

STATE = sys.argv[1] if len(sys.argv) > 1 else "initial"


class Harness(App):
    def build(self):
        data_dir = tempfile.mkdtemp(prefix="paynet-render-")
        if STATE.startswith("install_count"):
            reporter = InstallReporter(data_dir, "", version_name="1.0.0-test")
            screen = InstallCountScreen(
                reporter, lambda open_main: print("FINISH", open_main))
            if STATE == "install_count_saving":
                Clock.schedule_once(lambda *_: screen._save(True), 0.4)
            return screen

        sim = "jio" if STATE == "jio" else "airtel"
        prefs = PrefsStore(data_dir, "PayNetPrefs")
        prefs.put("selected_primary_sim", sim)
        results = TestResultsManager(data_dir)
        if STATE == "ready":
            results.save_test_results(TestResults(ussdEnabled=True))
        helper = TestConfigurationHelper(
            prefs, results,
            permission_manager=PermissionManager(checker=lambda _p: True),
            dial=lambda _number: None)
        helper.initialize()
        if STATE == "ussd_progress":
            helper.initiate_call(CallType.USSD)
        elif STATE == "ussd_confirm":
            helper.ussd_testing = True
            helper.show_ussd_configuration_options = True
        elif STATE == "upi123_progress":
            helper.upi123_testing = True
            helper.show_upi123_dialog = True
        screen = TestConfigurationScreen(
            helper,
            on_open_setup_review=lambda: print("REVIEW"),
            on_navigate_main=lambda: print("MAIN"))
        if STATE == "consent":
            Clock.schedule_once(lambda *_: screen._press_scan(), 0.3)
        return screen


app = Harness()
Clock.schedule_once(lambda *_: (
    print("SHOT", STATE, repr(Window.screenshot(f"/downloads/diagnostics-{STATE}.png"))),
    app.stop()), 0.9)
app.run()
