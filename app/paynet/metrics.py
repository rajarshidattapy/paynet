# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/metrics/InstallReporter.kt
# and app/src/main/java/com/paynet/app/metrics/InstallCountActivity.kt

"""One consented first-open receipt, independent of every payment repository.

DEVIATIONS (recorded in MIGRATION.md):
- The POST itself is an injected `poster` callable; the desktop build never
  contacts a collector (None = the request failed, keep the ID, retry later,
  exactly like Kotlin's IOException path). Real network wiring is feature 17.
- AtomicFile maps to a write-temp-then-rename in the data directory;
  `noBackupFilesDir` has no desktop equivalent (the Kotlin state test's
  "no_backup" path assertion ports as an under-the-data-dir assertion).
- Coroutines/Mutex map to a threading.RLock plus an injected scheduler for
  the 30 s retry backoff (manual in tests, threading.Timer by default).
- SystemClock.elapsedRealtime maps to an injected monotonic clock.
"""

import json
import os
import threading
import time
import uuid
from typing import Callable, Optional
from urllib.parse import urlparse

RETRY_DELAY_S = 30.0
REQUEST_TIMEOUT_MS = 8_000  # documented parity; the injected poster owns I/O

RECEIPT_FILENAME = "install-receipt.json"

# strings.xml
INSTALL_COUNT_TITLE = "Help us count PayNet."
INSTALL_COUNT_BODY = (
    "Share a one-time installation report when you have internet. It contains "
    "a random installation ID and app version. Our server also receives the "
    "connection IP address, but does not save it in the install counter.\n\n"
    "Your name, contacts, messages and payment details stay out of this "
    "report. Payments still work without internet.\n\n"
    "This is optional. Change your choice in Settings. Turning it off stops "
    "unsent reports; it does not remove a report already counted.")
INSTALL_COUNT_ALLOW = "Share installation"
INSTALL_COUNT_DECLINE = "Keep sharing off"


def valid_endpoint(value: str, debug: bool) -> bool:
    """InstallReporter.validEndpoint, ported 1:1: https only (debug also
    allows cleartext to 127.0.0.1), with a host and no userinfo, query or
    fragment."""
    try:
        uri = urlparse(value)
    except ValueError:
        return False
    if not uri.hostname or "@" in uri.netloc or uri.query or uri.fragment:
        return False
    if uri.scheme == "https":
        return True
    return bool(debug and uri.scheme == "http" and uri.hostname == "127.0.0.1")


class InstallReporter:
    """Port of the InstallReporter object as a constructed instance: the
    Kotlin object reads BuildConfig fields; here the endpoint, debug flag and
    version arrive at construction."""

    def __init__(
        self,
        directory: str,
        endpoint: str,
        debug: bool = False,
        version_name: str = "",
        clock: Callable[[], float] = time.monotonic,
        scheduler: Optional[Callable[[float, Callable[[], None]], None]] = None,
        poster: Optional[Callable[[str, dict], Optional[dict]]] = None,
    ) -> None:
        self._directory = directory
        self._endpoint = endpoint
        self._debug = debug
        self._version_name = version_name
        self._clock = clock
        # scheduler(delay_seconds, fn) fires fn once after the delay.
        self._scheduler = scheduler or self._default_scheduler
        self._poster = poster
        self._lock = threading.RLock()
        self._next_attempt = 0.0
        self._retry_scheduled = False
        self._storage_unavailable = False

    @staticmethod
    def _default_scheduler(delay: float, fn: Callable[[], None]) -> None:
        timer = threading.Timer(delay, fn)
        timer.daemon = True
        timer.start()

    # -- configuration ----------------------------------------------------

    def configured(self) -> bool:
        return valid_endpoint(self._endpoint, self._debug)

    # -- storage ----------------------------------------------------------

    @property
    def storage_unavailable(self) -> bool:
        return self._storage_unavailable

    def _path(self) -> str:
        return os.path.join(self._directory, RECEIPT_FILENAME)

    def _read(self) -> dict:
        try:
            with open(self._path(), encoding="utf-8") as handle:
                state = json.load(handle)
            return state if isinstance(state, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, state: dict) -> None:
        # AtomicFile port: write a sibling temp file, then rename.
        tmp = self._path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(state, handle)
        os.replace(tmp, self._path())

    # -- consent ----------------------------------------------------------

    def needs_choice(self) -> bool:
        if not self.configured() or self._storage_unavailable:
            return False
        return "consent" not in self._read()

    def choose(self, allow: bool) -> None:
        with self._lock:
            state = self._read()
            state["consent"] = allow
            if allow and "id" not in state:
                state["id"] = str(uuid.uuid4())
            try:
                self._write(state)
            except OSError:
                # A reporting-storage failure must never prevent payments or
                # force consent.
                self._storage_unavailable = True
        if allow:
            self.report()

    # -- reporting ----------------------------------------------------------

    def report(self) -> None:
        if not self.configured() or self._storage_unavailable:
            return
        with self._lock:
            try:
                state = self._read()
                if not state.get("consent") or state.get("sent"):
                    return
                now = self._clock()
                if now < self._next_attempt:
                    if not self._retry_scheduled:
                        self._retry_scheduled = True
                        wait = self._next_attempt - now

                        def _retry():
                            with self._lock:
                                self._retry_scheduled = False
                            self.report()

                        self._scheduler(wait, _retry)
                    return
                self._next_attempt = now + RETRY_DELAY_S
                payload = {"installation_id": state["id"],
                           "version": self._version_name}
                # DEVIATION: the injected poster stands in for the
                # HttpURLConnection POST; None means failure (IOException
                # path): keep the same ID and retry on a later event.
                response = self._poster(self._endpoint, payload) if self._poster else None
                if response is not None and response.get("registered"):
                    state["sent"] = True
                    self._write(state)
            except (KeyError, TypeError, ValueError, OSError):
                # Malformed local state or a storage failure: never crash the
                # caller and never acknowledge an unexpected response.
                return


# ---------------------------------------------------------------------------
# metrics/InstallCountActivity.kt: the consent screen.
# ---------------------------------------------------------------------------

from kivy.metrics import dp  # noqa: E402
from kivy.uix.boxlayout import BoxLayout  # noqa: E402
from kivy.uix.label import Label  # noqa: E402

from paynet import theme  # noqa: E402
from paynet.ui.onboarding import OnboardingDialogAction  # noqa: E402


class InstallCountScreen(BoxLayout):
    """InstallCountActivity: title, body, then the share/keep-off pair.
    Choosing either saves through InstallReporter.choose and finishes;
    unless launched from settings, finishing continues to MainActivity."""

    def __init__(self, reporter: InstallReporter, on_finished,
                 from_settings: bool = False, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        super().__init__(**kwargs)
        self._reporter = reporter
        self._on_finished = on_finished
        self._from_settings = from_settings
        self.saving = False
        self.padding = (dp(28), dp(28), dp(28), dp(28))
        self.spacing = dp(20)

        self._title = Label(text=INSTALL_COUNT_TITLE, font_size="34sp",
                            color=(1, 1, 1, 1), bold=True,
                            halign="left", valign="top",
                            size_hint=(1, None))
        self._title.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
        self._title.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1]))
        self._body = Label(text=INSTALL_COUNT_BODY, font_size="16sp",
                           color=theme.TEXT_LIGHT_GRAY, halign="left", valign="top",
                           size_hint=(1, None))
        self._body.line_height = 24 / 16
        self._body.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
        self._body.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1]))

        self._allow = OnboardingDialogAction(INSTALL_COUNT_ALLOW,
                                             lambda: self._save(True))
        self._decline = OnboardingDialogAction(INSTALL_COUNT_DECLINE,
                                               lambda: self._save(False),
                                               secondary=True)

        self.add_widget(BoxLayout(size_hint=(1, 1)))  # vertical centering spacer
        self.add_widget(self._title)
        self.add_widget(self._body)
        self.add_widget(self._allow)
        self.add_widget(self._decline)
        self.add_widget(BoxLayout(size_hint=(1, 1)))

    def _save(self, allow: bool) -> None:
        if self.saving:
            return
        self.saving = True
        self._allow.disabled = True
        self._decline.disabled = True
        self._reporter.choose(allow)
        # Kotlin: unless from_settings, continue to MainActivity; then finish.
        self._on_finished(not self._from_settings)
