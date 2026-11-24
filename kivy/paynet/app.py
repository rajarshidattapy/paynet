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
from kivy.graphics import Color as KvColor, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen, ScreenManager

from paynet import onboarding, theme
from paynet import setup as setup_logic
from paynet.db.database import Database
from paynet.db.settings import PrefsStore, SettingsRepository, TestResultsManager
from paynet.payment.initiate import TransferInitiator
from paynet.payment.session import PaymentSessionManager
from paynet.permissions import PermissionManager
from paynet.repository import TransactionRepository
from paynet.sms.detector import TransactionDetector
from paynet.telephony.call_manager import CallManager
from paynet.telephony.coordinator import CallStateCoordinator
from paynet.ui.history import HistoryScreen, TransactionDetailView
from paynet.ui.home import HomeScreen, home_bank_name
from paynet.ui.home_appearance import HomeAppearance
from paynet.ui.home_legacy import LegacyHomeScreen
from paynet.ui.pay_contact import PayContactDialog
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
        self.settings = SettingsRepository(data_dir)
        self.database = Database(os.path.join(data_dir, "paynet.db"))
        self.repository = TransactionRepository(self.database)
        self.main_view_model = MainViewModel()
        self.transaction_view_model = TransactionViewModel(self.repository)
        # One telephony listener for the whole app; no adapter off-device.
        self.call_coordinator = CallStateCoordinator(telephony=None)
        self.payment_session_manager = PaymentSessionManager(
            store=self.repository, coordinator=self.call_coordinator)
        # The operation-window detector; SMS ingestion itself is wired to
        # the platform receiver in feature 17. It owns a separate prefs
        # file, as TransactionDetector.getInstance does on Android.
        self.transaction_detector = TransactionDetector(
            PrefsStore(data_dir, "TransactionDetector"))
        # Feature 16: metrics/InstallReporter. DEVIATION: the BuildConfig
        # INSTALL_METRICS_URL gradle property maps to an environment variable;
        # empty means unconfigured, exactly like the Kotlin default.
        from paynet.metrics import InstallReporter
        self.install_reporter = InstallReporter(
            data_dir,
            os.environ.get("PAYNET_INSTALL_METRICS_URL", ""),
            version_name="1.0.0-sms")
        # Feature 17: the Android platform bindings. create_bindings()
        # returns None off-device; every seam below then keeps its
        # device-only no-op default and nothing platform-side is touched.
        from paynet import platform as paynet_platform
        self.bindings = paynet_platform.create_bindings()
        if self.bindings is not None:
            self.call_coordinator = CallStateCoordinator(
                telephony=self.bindings.telephony_adapter)
            self.install_reporter.poster = self.bindings.metrics_poster
            self.permission_manager = PermissionManager(
                self.bindings.permission_checker,
                can_draw_overlays=self.bindings.permission_checker.can_draw_overlays)
            self.call_manager = CallManager(self.bindings.phone_platform)
        else:
            self.permission_manager = PermissionManager()
            self.call_manager = None


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
        self._home_screen = home_screen
        self.home = self._make_home(appearance, results, bank)
        home_screen.add_widget(self.home)
        sm.add_widget(home_screen)
        self.sm = sm
        self._detail_overlay = None

        # Feature 12: onboarding routing. AppearanceSetupActivity runs when
        # the one-time introduction is unfinished; SetupActivity runs until
        # setup_completed; otherwise MainActivity (home).
        self._setup_helper = setup_logic.SetupHelper(
            self.container.prefs, self.container.test_results,
            show_toast=self._show_toast,
            navigate_to_test_configuration=self._open_setup_required)
        from paynet.ui.setup import SetupScreen
        self.setup_screen = Screen(name="setup")
        self.setup_screen.add_widget(SetupScreen(
            self._setup_helper, self.container.prefs))
        sm.add_widget(self.setup_screen)

        from paynet.ui.appearance import AppearanceScreen
        self.appearance_screen = Screen(name="appearance")
        self.appearance_screen.add_widget(AppearanceScreen(
            self.container.prefs,
            on_open_home=self._finish_appearance,
            on_review_setup=lambda: setattr(sm, "current", "setup")))
        sm.add_widget(self.appearance_screen)

        # Feature 13: SettingsActivity as its own screen, refreshed on entry.
        from paynet.ui.settings import SettingsScreen
        self._settings_widget = SettingsScreen(
            self.container.prefs, self.container.settings,
            self.container.test_results, self.container.repository,
            on_back=self._leave_settings,
            on_open_setup=self._reopen_setup,
            on_appearance_changed=self._apply_appearance_to_home,
            install_reporter_configured=self.container.install_reporter.configured,
            on_open_install_count=lambda: self._open_install_count(from_settings=True),
            permission_provider=self._permission_provider)
        self.settings_screen = Screen(name="settings")
        self.settings_screen.add_widget(self._settings_widget)
        self.settings_screen.bind(
            on_enter=lambda *_: self._settings_widget.refresh())
        sm.add_widget(self.settings_screen)

        # Feature 16: TestConfigurationActivity + InstallCountActivity.
        from paynet.metrics import InstallCountScreen
        from paynet.ui.diagnostics import (TestConfigurationHelper,
                                           TestConfigurationScreen)
        reporter = self.container.install_reporter
        self._diagnostics_helper = TestConfigurationHelper(
            self.container.prefs, self.container.test_results,
            show_toast=self._show_toast,
            navigate_to_main=lambda: setattr(
                sm, "current", onboarding.route_after_payments(self.container.prefs)),
            # DEVIATION: the phone-permission launcher and the *99# dial are
            # device-only (feature 17); nothing is ever dialled here.
            request_phone_permissions=lambda: None,
            dial=None)
        # Feature 17: on Android the permission launcher and the *99# dial
        # reach the platform bindings; off-device they stay no-ops.
        if self.container.bindings is not None:
            self._diagnostics_helper._request_phone_permissions = (
                self.container.bindings.permission_requester.request_phone_permissions)
            self._diagnostics_helper._dial = (
                lambda number: self.container.bindings.phone_platform.start_call(
                    "tel:" + number.replace("#", "%23")))
        self._diagnostics_helper.initialize()
        self.diagnostics_screen = Screen(name="diagnostics")
        self.diagnostics_screen.add_widget(TestConfigurationScreen(
            self._diagnostics_helper,
            on_open_setup_review=lambda: setattr(sm, "current", "setup"),
            on_navigate_main=lambda: setattr(
                sm, "current", onboarding.route_after_payments(self.container.prefs))))
        sm.add_widget(self.diagnostics_screen)

        self._install_count_from_settings = False
        self.install_count_screen = Screen(name="install_count")
        self.install_count_screen.add_widget(InstallCountScreen(
            reporter, self._finish_install_count,
            from_settings=self._install_count_from_settings))
        sm.add_widget(self.install_count_screen)

        if onboarding.needs_appearance(self.container.prefs):
            sm.current = "appearance"
        elif not self.container.prefs.get("setup_completed", False):
            sm.current = "setup"
        elif reporter.needs_choice():
            # MainActivity.onCreate: the consent screen runs before anything
            # else on the first consented open.
            sm.current = "install_count"

        # Feature 9: TransactionHistoryActivity as the second screen.
        vm0 = self.container.transaction_view_model
        self.history = HistoryScreen(
            vm0,
            on_back=lambda: setattr(sm, "current", "home"),
            on_delete=lambda tx: vm0.delete_transaction(tx),
        )
        history_screen = Screen(name="history")
        history_screen.add_widget(self.history)
        history_screen.bind(on_enter=lambda *_: vm0.load_history())
        sm.add_widget(history_screen)

        # MainDialogs: the selected transaction's receipt opens over
        # whichever screen is current.
        vm0.selected_transaction.subscribe(
            lambda tx: Clock.schedule_once(lambda *_: self._show_selected(tx), 0)
        )

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
        # PayNetApplication: report on foreground events when configured.
        home_screen.bind(on_enter=lambda *_: self.container.install_reporter.report())
        Clock.schedule_once(lambda *_: self._refresh_home(), 0)
        # ScreenManager accepts only Screen children, so dialogs, toasts and
        # receipt overlays layer onto a plain root above it.
        self._root = FloatLayout()
        self._root.add_widget(sm)
        self._result_screen = None
        # Feature 17: the platform SMS receiver. On Android the Java bridge
        # (PayNetSmsReceiver -> PayNetSmsBridge) forwards each assembled PDU
        # set here, mirroring SimpleSMSReceiver.onReceive; the Kotlin's
        # NotificationHelper post becomes a system notification.
        if self.container.bindings is not None:
            self._register_sms_receiver()
        return self._root

    def _permission_provider(self):
        # Settings parity: live grants from the platform, never stored prefs.
        manager = self.container.permission_manager
        return {
            "phone": manager.has_phone_permissions(),
            "camera": manager.has_camera_permission(),
            "contacts": manager.has_contact_permission(),
            "overlay": manager.has_overlay_permission(),
        }

    def _register_sms_receiver(self):
        from paynet.sms import pipeline
        from paynet.sms.notifier import notify_result
        from paynet.sms.receiver import SimpleSMSReceiver
        bindings = self.container.bindings
        self._sms_receiver = SimpleSMSReceiver(
            self.container.transaction_detector,
            lambda detector, sender, body: pipeline.ingest(
                detector, sender, body,
                session_manager=self.container.payment_session_manager,
                repository=self.container.repository,
                notifier=lambda result: notify_result(
                    result, post=bindings.notifier.post),
                open_result=self._open_payment_result))
        bindings.register_sms_bridge(self._sms_receiver.handle_sms)

    def _open_payment_result(self, info):
        # Ingestion runs on the bridge's background thread; screens only
        # change on the Kivy main thread.
        Clock.schedule_once(lambda *_: self._show_payment_result(info), 0)

    def _show_payment_result(self, info):
        # DEVIATION: the Kotlin surfaces a background payment only as a
        # heads-up notification; a confirmation arriving while the app is in
        # the foreground additionally shows the feature-14 result screen.
        from paynet.ui.result import PaymentResultScreen
        if self._result_screen is not None:
            self.sm.remove_widget(self._result_screen)
        widget = PaymentResultScreen(
            on_done=lambda: setattr(self.sm, "current", "home"))
        widget.render(
            transaction_id=info.get("transaction_id", "N/A"),
            amount=info.get("amount", "0"),
            status=info.get("status", "UNKNOWN"),
            bank_name=info.get("bank_name", "Bank"),
            timestamp_ms=info.get("timestamp"),
            upi_id=info.get("upi_id"),
            transaction_type=info.get("transaction_type", "DEBIT"),
            recipient_name=info.get("recipient_name"),
            phone_number=info.get("phone_number"))
        self._result_screen = Screen(name="payment_result")
        self._result_screen.add_widget(widget)
        self.sm.add_widget(self._result_screen)
        self.sm.current = "payment_result"

    def _make_home(self, appearance, results, bank):
        # HomeDashboard.kt: the legacy dashboard only when the appearance is
        # classic and not monochrome.
        if appearance.classic and not appearance.monochrome:
            return LegacyHomeScreen(
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
        return HomeScreen(
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

    def _finish_appearance(self):
        """AppearanceSetupActivity.openHome: rebuild home with the chosen
        appearance and leave the introduction on the back stack."""
        self._apply_appearance_to_home()
        self.sm.current = "home"

    def _apply_appearance_to_home(self):
        """Re-read appearance + bank prefs and rebuild the home screen
        (rememberMainScreenState's ON_RESUME re-read, applied to the
        whole widget because the bank/appearance are baked in)."""
        container = self.container
        appearance = HomeAppearance.read(container.prefs)
        results = container.test_results.get_test_results()
        bank = container.prefs.get("selected_bank", "hdfc")
        self._home_screen.remove_widget(self.home)
        self.home = self._make_home(appearance, results, bank)
        self._home_screen.add_widget(self.home)
        self._refresh_home()

    def _leave_settings(self):
        self._apply_appearance_to_home()
        self.sm.current = "home"

    def _reopen_setup(self):
        """Clear-data lands on a fresh setup screen (the saved selections
        were just wiped, so the old widget's state is stale)."""
        from paynet.ui.setup import SetupScreen
        self.setup_screen.clear_widgets()
        self.setup_screen.add_widget(SetupScreen(
            self._setup_helper, self.container.prefs))
        self.sm.current = "setup"

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
        self.sm.current = "settings"

    def _open_history(self):
        self.sm.current = "history"

    def _show_selected(self, transaction):
        if self._detail_overlay is not None:
            self._root.remove_widget(self._detail_overlay)
            self._detail_overlay = None
        if transaction is not None:
            vm = self.container.transaction_view_model
            self._detail_overlay = TransactionDetailView(
                transaction,
                on_dismiss=vm.clear_selected_transaction,
                on_delete=lambda tx: (vm.delete_transaction(tx),
                                      vm.clear_selected_transaction()),
            )
            self._detail_overlay.size = self._root.size
            self._detail_overlay.pos = self._root.pos
            self._root.add_widget(self._detail_overlay)

    def _open_transaction(self, payment):
        self.container.transaction_view_model.select_transaction(payment.id)

    def _open_scanner(self):
        # MainActivityHelper.startQRScanning gate, then feature 11's screen.
        # The phone-permission request leg is device-only (feature 17).
        blocked = setup_logic.get_scan_to_pay_blocked_message(self.container.prefs)
        if blocked is not None:
            self._show_toast(blocked)
            return
        results = self.container.test_results.get_test_results()
        if not (results and results.ussdEnabled):
            self._open_setup_required()
            return
        # Feature 11: QRScannerActivity as its own screen. The camera
        # preview and torch stay device-only; feature 17 wires the dial,
        # the call-permission gate and the gallery decode through the
        # platform bindings.
        from paynet.ui.qr_scanner import QRScannerScreen
        scanner_kwargs = {}
        if self.container.bindings is not None:
            scanner_kwargs = {
                # The scanner passes the full tel: URI (USSD_DIAL_URI).
                "dial": self.container.bindings.phone_platform.start_call,
                "has_call_permission": (
                    self.container.permission_manager.has_phone_permissions),
                "request_call_permission": (
                    self.container.bindings.permission_requester
                    .request_phone_permissions),
                "decode_gallery_image": (
                    self.container.bindings.decode_gallery_image),
            }
        self._scanner = QRScannerScreen(
            self.container.payment_session_manager,
            detector=self.container.transaction_detector,
            show_toast=self._show_toast,
            blocked_message=lambda: setup_logic.get_scan_to_pay_blocked_message(
                self.container.prefs),
            on_close=self._close_scanner,
            name="qr_scanner", **scanner_kwargs)
        self.sm.add_widget(self._scanner)
        self.sm.current = "qr_scanner"

    def _close_scanner(self, _result):
        scanner = getattr(self, "_scanner", None)
        if scanner is None:
            return
        scanner.controller.on_destroy(is_finishing=True)
        self.sm.remove_widget(scanner)
        self._scanner = None
        self.sm.current = "home"

    def _show_toast(self, message):
        # Toast port: transient bottom bar, same shape as the history
        # screen's snackbar.
        if getattr(self, "_toast", None) is not None:
            self._root.remove_widget(self._toast)
        bar = FloatLayout(size_hint=(None, None), size=(dp(300), dp(44)))
        with bar.canvas.before:
            KvColor(rgba=theme.MEDIUM_GRAY)
            bar._bg = RoundedRectangle(radius=[dp(12)])
        bar.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos),
                 size=lambda w, _: setattr(w._bg, "size", w.size))
        bar.add_widget(Label(text=message, font_size="13sp",
                             color=(1, 1, 1, 1)))
        bar.center_x = self._root.center_x
        bar.y = self._root.y + dp(24)
        self._toast = bar
        self._root.add_widget(bar)
        Clock.schedule_once(self._dismiss_toast, 3)

    def _dismiss_toast(self, *_):
        if getattr(self, "_toast", None) is not None:
            self._root.remove_widget(self._toast)
            self._toast = None

    def _open_pay_contact(self):
        if getattr(self, "_pay_contact", None) is not None:
            return
        vm = self.container.transaction_view_model
        self._pay_contact = PayContactDialog(
            on_dismiss=self._close_pay_contact,
            on_confirm=self._confirm_pay_contact,
            show_toast=self._show_toast)
        self._pay_contact.size = self._root.size
        self._pay_contact.pos = self._root.pos
        self._root.add_widget(self._pay_contact)

    def _close_pay_contact(self):
        if getattr(self, "_pay_contact", None) is not None:
            self._root.remove_widget(self._pay_contact)
            self._pay_contact = None

    def _confirm_pay_contact(self, phone, amount, name):
        self._close_pay_contact()
        self._initiator().initiate_transfer(phone, amount,
                                            recipient_name=name)

    def _initiator(self):
        if getattr(self, "_transfer_initiator", None) is None:
            self._transfer_initiator = TransferInitiator(
                self.container.test_results,
                self.container.payment_session_manager,
                show_toast=self._show_toast,
                on_setup_required=self._open_setup_required,
            )
        return self._transfer_initiator

    def _open_setup_required(self):
        # Kotlin: navigateToTestConfiguration() (feature 16).
        if not self.container.prefs.get("setup_completed", False):
            self.sm.current = "setup"
        else:
            self.sm.current = "diagnostics"

    def _open_diagnostics(self):
        self.sm.current = "diagnostics"

    def _open_install_count(self, from_settings=False):
        # metrics/InstallCountActivity.
        self._install_count_from_settings = from_settings
        self.sm.current = "install_count"

    def _finish_install_count(self, _open_main):
        # The screen baked its from_settings flag at build time; the app's
        # flag (set by _open_install_count) is the current one.
        if not self._install_count_from_settings:
            self.sm.current = onboarding.route_after_payments(self.container.prefs)
        else:
            self.sm.current = "settings"
