# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Dev-only headless render harness for the pay-contact dialog (feature 10).

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
from paynet.ui.pay_contact import Contact  # noqa: E402


class FakeProvider:
    def has_contact_permission(self):
        return True

    def request_contact_permission(self, on_result):
        on_result(True)

    def load_contacts(self):
        return [
            Contact("1", "Kirana Store", "9123456780"),
            Contact("2", "Rahul Sharma", "9876501234"),
            Contact("3", "Airtel Prepaid", "9000011111"),
        ]


def run(state: str = "empty") -> None:
    data_dir = tempfile.mkdtemp(prefix="paynet-render-pc-")
    app = PayNetApp(data_dir=data_dir)

    def seed(*_):
        app.container.prefs.put("selected_bank", "hdfc")
        app.container.test_results.save_test_results(
            TestResults(ussdEnabled=True, upi123Enabled=True))
        app._open_pay_contact()
        if state in ("picker", "permission"):
            app._pay_contact._provider = FakeProvider()
        dialog = app._pay_contact
        if state == "filled":
            dialog.phone_field.input.text = "9123456780"
            dialog.amount_field.input.text = "240"
        elif state == "overcap":
            dialog.phone_field.input.text = "9123456780"
            dialog.amount_field.input.text = "6000"
        elif state == "picker":
            dialog.choose_contact()
        elif state == "selected":
            dialog._contact_selected(Contact("1", "Kirana Store", "9123456780"))
            dialog.amount_field.input.text = "240"

    def shoot(*_):
        fn = Window.screenshot(f"/downloads/paycontact-{state}.png")
        print("SHOT", state, repr(fn))
        app.stop()

    Clock.schedule_once(seed, 0)
    Clock.schedule_once(shoot, 1.4)
    app.run()


if __name__ == "__main__":
    import sys

    run(sys.argv[1] if len(sys.argv) > 1 else "empty")
