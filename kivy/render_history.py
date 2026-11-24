# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Dev-only headless render harness for the history screen (feature 9).

import os
import tempfile
import time

os.environ.setdefault("KIVY_NO_ARGS", "1")

from kivy.config import Config

Config.set("graphics", "width", "412")
Config.set("graphics", "height", "892")
Config.set("graphics", "borderless", "1")
Config.set("graphics", "resizable", "0")

from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402

from paynet.app import PayNetApp  # noqa: E402
from paynet.db.models import Transaction  # noqa: E402

HOUR = 3_600_000
DAY = 86_400_000


def run(state: str = "list") -> None:
    data_dir = tempfile.mkdtemp(prefix="paynet-render-history-")
    app = PayNetApp(data_dir=data_dir)

    def seed(*_):
        now = int(time.time() * 1000)
        app.container.prefs.put("selected_bank", "hdfc")
        app.container.repository.save_transactions([
            Transaction(transactionId="t1", amount="240.00", status="SUCCESS",
                        bankName="HDFC Bank", smsExcerpt="Rs 240.00 paid",
                        timestamp=now - 2 * HOUR, upiId="kiranastore@upi",
                        recipientName="Kirana Store",
                        phoneNumber="9123456780", bankRef="AX123456"),
            Transaction(transactionId="t2", amount="100.00", status="FAILED",
                        bankName="HDFC Bank", smsExcerpt="Rs 100.00",
                        timestamp=now - 5 * HOUR, upiId="9123456780@upi",
                        recipientName="9123456780"),
            Transaction(transactionId="t3", amount="1499.50", status="USER_CONFIRMED",
                        bankName="HDFC Bank", smsExcerpt="Rs 1499.50",
                        timestamp=now - DAY - 3 * HOUR,
                        recipientName="Airtel Prepaid"),
            Transaction(transactionId="t4", amount="", status="PENDING",
                        bankName="HDFC Bank", smsExcerpt="",
                        timestamp=now - 3 * DAY, recipientName="Rahul"),
            Transaction(transactionId="t5", amount="60.00", status="CANCELLED",
                        bankName="HDFC Bank", smsExcerpt="Rs 60.00",
                        timestamp=now - 40 * DAY, recipientName="Tea Stall"),
        ])
        app._open_history()

    def prepare(*_):
        if state == "search":
            app.history._toggle_search()
            app.history.search_bar.input.text = "kirana"
        elif state == "detail":
            tx = app.container.repository.get_all_transactions()[0]
            app.history._open_detail(tx)
        elif state == "delete":
            tx = app.container.repository.get_all_transactions()[0]
            app.history._open_detail(tx)
            app.history._detail._ask_delete()
        elif state == "empty":
            app.history._query = "zzz-no-match"
            app.history._rebuild()

    def shoot(*_):
        fn = Window.screenshot(f"/downloads/history-{state}.png")
        print("SHOT", state, repr(fn))
        app.stop()

    Clock.schedule_once(seed, 0)
    Clock.schedule_once(prepare, 0.6)
    Clock.schedule_once(shoot, 1.4)
    app.run()


if __name__ == "__main__":
    import sys

    run(sys.argv[1] if len(sys.argv) > 1 else "list")
