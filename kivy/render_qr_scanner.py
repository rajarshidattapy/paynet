# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Dev-only headless render harness for the QR scanner screen (feature 11).

import os
import tempfile

os.environ.setdefault("KIVY_NO_ARGS", "1")

from kivy.config import Config

Config.set("graphics", "width", "412")
Config.set("graphics", "height", "892")
Config.set("graphics", "borderless", "1")
Config.set("graphics", "resizable", "0")

from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402

from paynet.app import PayNetApp  # noqa: E402
from paynet.db.settings import TestResults  # noqa: E402

GOOD_QR = "upi://pay?pa=kirana@okhdfcbank&pn=Kirana%20Store&am=240.50"


def run(state: str = "scanning") -> None:
    data_dir = tempfile.mkdtemp(prefix="paynet-render-qr-")
    app = PayNetApp(data_dir=data_dir)

    def seed(*_):
        app.container.prefs.put("selected_bank", "hdfc")
        app.container.test_results.save_test_results(
            TestResults(ussdEnabled=True, upi123Enabled=True))
        app._open_scanner()
        screen = app._scanner
        # Fake the dial so the flow proceeds without telephony.
        screen.controller._dial = lambda uri: True
        screen.controller._has_call_permission = lambda: True
        if state == "invalid":
            screen.controller.process_qr_code("https://example.com")
        elif state == "waiting":
            screen.controller.process_qr_code(GOOD_QR)
            # The Clock-scheduled dial lands in 1 s; triggering it now is
            # idempotent thanks to the dial-once guard.
            screen.controller.dial_ussd()
        elif state == "steps":
            screen.controller.process_qr_code(GOOD_QR)
            screen.controller.dial_ussd()
            screen._expand_instructions()

    def shoot(*_):
        fn = Window.screenshot(f"/downloads/qrscanner-{state}.png")
        print("SHOT", state, repr(fn))
        app.stop()

    Clock.schedule_once(seed, 0)
    Clock.schedule_once(shoot, 1.4)
    app.run()


if __name__ == "__main__":
    import sys

    run(sys.argv[1] if len(sys.argv) > 1 else "scanning")
