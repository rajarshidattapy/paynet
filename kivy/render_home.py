# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Dev-only headless render harness for visual verification of HomeScreen.
# Not part of the shipped app; screenshots are gitignored.

import os
import tempfile

os.environ.setdefault("KIVY_NO_ARGS", "1")
# log silenced only when caller sets KIVY_NO_CONSOLELOG

from kivy.config import Config

Config.set("graphics", "width", "412")
Config.set("graphics", "height", "892")
Config.set("graphics", "borderless", "1")
Config.set("graphics", "resizable", "0")

from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402

from paynet.app import PayNetApp  # noqa: E402
from paynet.db.models import Transaction  # noqa: E402
from paynet.db.settings import TestResults  # noqa: E402


def run(state: str = "payments", legacy: bool = False) -> None:
    data_dir = tempfile.mkdtemp(prefix="paynet-render-")
    if legacy:
        # Classic appearance must exist before build() reads it.
        from paynet.db.settings import PrefsStore
        prefs = PrefsStore(data_dir, "PayNetPrefs")
        prefs.put("home_classic", True)
        prefs.put("home_monochrome", False)
    app = PayNetApp(data_dir=data_dir)

    def seed(*_):
        # Seed prefs + payments the way onboarding/payment flow would have.
        # build() has run by now, so the container exists.
        app.container.prefs.put("selected_bank", "hdfc")
        app.container.test_results.save_test_results(
            TestResults(ussdEnabled=True, upi123Enabled=True)
        )
        app.container.repository.save_transactions([
            Transaction(transactionId="t1", amount="240.00", status="SUCCESS",
                        bankName="HDFC Bank", smsExcerpt="Rs 240.00 paid to Kirana Store",
                        timestamp=1_763_900_000_000, upiId="kiranastore@upi",
                        recipientName="Kirana Store"),
            Transaction(transactionId="t2", amount="100.00", status="FAILED",
                        bankName="HDFC Bank", smsExcerpt="Rs 100.00 to 9123456780",
                        timestamp=1_763_813_400_000, upiId="9123456780@upi",
                        recipientName="9123456780"),
        ])
        app._refresh_home()

    def prepare(*_):
        if state == "loading":
            app.home.show_loading()
        elif state == "empty":
            app.home.show_payments([])
        elif state == "error":
            app.home.show_error()
        else:
            app.home.show_payments(
                app.container.transaction_view_model.recent_transactions.value
            )

    def shoot(*_):
        fn = Window.screenshot(f"/downloads/home-{state}.png")
        print("SHOT", state, repr(fn))
        app.stop()

    Clock.schedule_once(seed, 0)
    Clock.schedule_once(prepare, 0.5)
    Clock.schedule_once(shoot, 1.2)
    app.run()


if __name__ == "__main__":
    import sys

    run(sys.argv[1] if len(sys.argv) > 1 else "payments",
        legacy="legacy" in sys.argv)
