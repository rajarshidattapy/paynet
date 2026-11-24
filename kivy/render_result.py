# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Headless render harness for feature 14 (payment result screen + prompts).
# Usage: xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 python3 render_result.py STATE

import os
import sys

os.environ.setdefault("KIVY_NO_ARGS", "1")
from kivy.config import Config

Config.set("graphics", "width", "412")
Config.set("graphics", "height", "892")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.floatlayout import FloatLayout

from paynet.ui.prompts import PaymentPrompt, ussd_progress_dialog
from paynet.ui.result import PaymentResultScreen

STATE = sys.argv[1] if len(sys.argv) > 1 else "success"

STATES = {
    "success": dict(transaction_id="HDFC912345_1764014820000", amount="1500.0",
                    status="SUCCESS", bank_name="HDFC Bank",
                    timestamp_ms=1764014820000, upi_id="asha@okhdfc",
                    transaction_type="DEBIT", recipient_name="Asha Sharma"),
    "failed": dict(transaction_id="UTIB_9988_1764014820000", amount="240.5",
                   status="FAILED", bank_name="ICICI Bank",
                   timestamp_ms=1764014820000, transaction_type="DEBIT",
                   recipient_name="Asha Sharma"),
    "needs_review": dict(transaction_id="N/A", amount="999",
                         status="NEEDS_REVIEW", bank_name="State Bank of India",
                         timestamp_ms=1764014820000, transaction_type="DEBIT",
                         phone_number="+919812345678"),
    "unverified": dict(transaction_id="txn-42", amount="60",
                       status="UNKNOWN", bank_name="Bank",
                       timestamp_ms=1764014820000, transaction_type="CREDIT",
                       recipient_name="Ravi"),
}


class Harness(App):
    def build(self):
        if STATE in STATES:
            screen = PaymentResultScreen(on_done=lambda: print("DONE"),
                                         animations_enabled=False)
            screen.render(**STATES[STATE])
            return screen
        root = FloatLayout()
        with root.canvas.before:
            from kivy.graphics import Color, RoundedRectangle
            Color(0, 0, 0, 1)
            root._bg = RoundedRectangle(pos=root.pos, size=root.size, radius=[0])
        root.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                  size=lambda w, _: setattr(w._bg, "size", w.size))
        if STATE == "prompt":
            root.add_widget(PaymentPrompt(on_answer=lambda yes: print("ANSWER", yes),
                                          on_later=lambda: print("LATER")).build())
        elif STATE == "notice":
            root.add_widget(PaymentPrompt(notice=True,
                                          on_later=lambda: print("LATER")).build())
        elif STATE == "ussd":
            dialog = ussd_progress_dialog()
            dialog._reveal_shortcuts()
            root.add_widget(dialog.build())
        return root


app = Harness()
Clock.schedule_once(lambda *_: (
    print("SHOT", STATE, repr(Window.screenshot(f"/downloads/result-{STATE}.png"))),
    app.stop()), 0.9)
app.run()
