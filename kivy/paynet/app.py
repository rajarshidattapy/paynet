# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/PayNetApplication.kt and
# app/src/main/java/com/paynet/app/di/AppContainer.kt

"""PayNet Kivy application shell.

Composition root: AppContainer mirrors the Kotlin hand-wired DI graph —
constructed here, referenced by every screen/service. Screens are added
feature by feature per MIGRATION.md; the shell (window, theme, navigation)
is stable from phase 2 onward.
"""

import os

os.environ.setdefault("KIVY_NO_ARGS", "1")

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.screenmanager import Screen, ScreenManager

from paynet import theme  # noqa: F401  (imported for screens)
from paynet.db.database import Database
from paynet.db.settings import PrefsStore, TestResultsManager
from paynet.repository import TransactionRepository
from paynet.ui.home import HomeScreen, home_bank_name
from paynet.ui.home_appearance import HomeAppearance
from paynet.ui.home_legacy import LegacyHomeScreen
from paynet.viewmodels import MainViewModel, TransactionViewModel


class AppContainer:
    """The manual, framework-free composition root (port of di/AppContainer).
    Process-scoped services are constructed and held here; everything else
    reaches them through the app instance."""

    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir = data_dir
        self.prefs = PrefsStore(data_dir, "PayNetPrefs")
        self.test_results = TestResultsManager(data_dir)
        self.database = Database(os.path.join(data_dir, "paynet.db"))
        self.repository = TransactionRepository(self.database)
        self.main_view_model = MainViewModel()
        self.transaction_view_model = TransactionViewModel(self.repository)


class PayNetApp(App):
    def __init__(self, data_dir=None, **kwargs):
        super().__init__(**kwargs)
        self._data_dir = data_dir

    def build(self):
        self.title = "PayNet"
        self.container = AppContainer(self._data_dir or self.user_data_dir)

        results = self.container.test_results.get_test_results()
        appearance = HomeAppearance.read(self.container.prefs)
        bank = self.container.prefs.get("selected_bank", "hdfc")

        sm = ScreenManager()
        home_screen = Screen(name="home")
        # HomeDashboard.kt: the legacy dashboard only when the appearance is
        # classic and not monochrome.
        if appearance.classic and not appearance.monochrome:
            self.home = LegacyHomeScreen(
                bank_name=home_bank_name(bank),
                monochrome=False,
                is_upi123_ready=bool(results and results.upi123Enabled),
                is_ussd_ready=bool(results and results.ussdEnabled),
                on_settings=self._open_settings,
                on_history=self._open_history,
                on_retry=self.container.transaction_view_model.refresh,
                on_transaction=self._open_transaction,
                on_scan=self._open_scanner,
                on_pay_contact=self._open_pay_contact,
            )
        else:
            self.home = HomeScreen(
                bank_id=bank,
                monochrome=appearance.monochrome,
                classic=appearance.classic,
                is_upi123_ready=bool(results and results.upi123Enabled),
                is_ussd_ready=bool(results and results.ussdEnabled),
                on_settings=self._open_settings,
                on_history=self._open_history,
                on_retry=self.container.transaction_view_model.refresh,
                on_transaction=self._open_transaction,
                on_scan=self._open_scanner,
                on_pay_contact=self._open_pay_contact,
            )
        home_screen.add_widget(self.home)
        sm.add_widget(home_screen)

        vm = self.container.transaction_view_model
        vm.recent_transactions.subscribe(
            lambda payments: Clock.schedule_once(
                lambda *_: self.home.show_payments(payments), 0
            )
        )
        vm.is_loading.subscribe(
            lambda loading: Clock.schedule_once(
                lambda *_: self.home.show_loading() if loading else None, 0
            )
        )
        home_screen.bind(on_enter=lambda *_: self._refresh_home())
        Clock.schedule_once(lambda *_: self._refresh_home(), 0)
        return sm

    def _refresh_home(self):
        # Port of rememberMainScreenState's ON_RESUME block: re-read the
        # readiness/appearance prefs and refresh the recent-payments list.
        results = self.container.test_results.get_test_results()
        self.home.is_upi123_ready = bool(results and results.upi123Enabled)
        self.home.is_ussd_ready = bool(results and results.ussdEnabled)
        self.home.is_scanning = False
        # The modern panel shows the scan state on the FAB; the legacy
        # variant rebuilds its action buttons.
        if hasattr(self.home, "history_panel"):
            self.home.history_panel.set_scan_state(self.home._scan_state(), True)
        elif hasattr(self.home, "update_readiness"):
            self.home.update_readiness(
                self.home.is_upi123_ready, self.home.is_ussd_ready, False)
        self.container.transaction_view_model.refresh()

    # Navigation targets arrive with their own features (MIGRATION.md);
    # until then these are deliberate no-ops.
    def _open_settings(self):
        pass

    def _open_history(self):
        pass

    def _open_transaction(self, payment):
        self.container.transaction_view_model.select_transaction(payment.id)

    def _open_scanner(self):
        pass

    def _open_pay_contact(self):
        pass
