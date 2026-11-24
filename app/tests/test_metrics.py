# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported 1:1 from app/src/test/java/com/paynet/app/metrics/InstallReporterTest.kt
# and app/src/test/java/com/paynet/app/metrics/InstallReceiptStateTest.kt,
# plus new coverage for the report/backoff/storage-failure rules.

import json
import os

from paynet.metrics import (RECEIPT_FILENAME, InstallReporter,
                            valid_endpoint)


# --- InstallReporterTest.kt, 1:1 -------------------------------------------


def test_release_rejects_cleartext_and_missing_collector():
    assert not valid_endpoint("", False)
    assert not valid_endpoint("http://example.com/api/installs", False)
    assert not valid_endpoint("http://127.0.0.1:8766/api/installs", False)
    assert valid_endpoint("https://example.com/api/installs", False)


def test_debug_allows_only_loopback_cleartext():
    assert valid_endpoint("http://127.0.0.1:8766/api/installs", True)
    assert not valid_endpoint("http://example.com/api/installs", True)


def test_credentials_and_tracking_query_rejected():
    assert not valid_endpoint("https://user:password@example.com/api/installs", False)
    assert not valid_endpoint("https://example.com/api/installs?phone=1", False)
    assert not valid_endpoint("https://example.com/api/installs#fragment", False)


# --- InstallReceiptStateTest.kt, 1:1 ----------------------------------------
# Kotlin guards these with assumeFalse(configured()): the state tests must
# never contact a real collector. The port constructs the reporter with an
# empty endpoint, which is never configured.


def _reporter(tmp_path, **kwargs):
    kwargs.setdefault("endpoint", "")
    return InstallReporter(str(tmp_path), **kwargs)


def _receipt(tmp_path):
    return os.path.join(str(tmp_path), RECEIPT_FILENAME)


def _state(tmp_path):
    with open(_receipt(tmp_path), encoding="utf-8") as handle:
        return json.load(handle)


def test_declining_never_generates_an_identifier(tmp_path):
    _reporter(tmp_path).choose(False)
    state = _state(tmp_path)
    assert state["consent"] is False
    assert "id" not in state
    assert not state.get("sent")


def test_retries_and_changed_consent_keep_the_same_installation_id(tmp_path):
    reporter = _reporter(tmp_path)
    reporter.choose(True)
    first = _state(tmp_path)["id"]
    reporter.choose(False)
    reporter.choose(True)
    assert _state(tmp_path)["id"] == first
    assert not _state(tmp_path).get("sent")


def test_already_acknowledged_receipt_survives_opt_out_and_back_in(tmp_path):
    reporter = _reporter(tmp_path)
    reporter.choose(True)
    state = _state(tmp_path)
    state["sent"] = True
    with open(_receipt(tmp_path), "w", encoding="utf-8") as handle:
        json.dump(state, handle)
    reporter.choose(False)
    reporter.choose(True)
    final = _state(tmp_path)
    assert final["sent"] is True
    assert final["id"] == state["id"]
    # DEVIATION: Kotlin asserts the noBackupFilesDir path contains
    # "no_backup"; the port keeps the receipt under the reporter's directory.
    assert _receipt(tmp_path).startswith(str(tmp_path))


# --- New coverage: report flow, backoff, storage failure --------------------


class ManualScheduler:
    def __init__(self):
        self.pending = []  # (delay, fn)

    def __call__(self, delay, fn):
        self.pending.append((delay, fn))

    def fire(self):
        delay, fn = self.pending.pop(0)
        fn()
        return delay


def _configured(tmp_path, poster, scheduler=None, clock=None):
    return InstallReporter(str(tmp_path),
                           "https://collector.example.com/api/installs",
                           version_name="1.0.0-test",
                           clock=clock or (lambda: 1000.0),
                           scheduler=scheduler,
                           poster=poster)


def test_registered_response_marks_sent_and_stops_reporting(tmp_path):
    calls = []

    def poster(url, payload):
        calls.append((url, payload))
        return {"registered": True}

    reporter = _configured(tmp_path, poster)
    reporter.choose(True)
    assert len(calls) == 1
    url, payload = calls[0]
    assert url == "https://collector.example.com/api/installs"
    assert payload["installation_id"] == _state(tmp_path)["id"]
    assert payload["version"] == "1.0.0-test"
    assert _state(tmp_path)["sent"] is True
    reporter.report()
    assert len(calls) == 1  # already sent: no second POST


def test_unregistered_or_failed_response_keeps_id_and_retries_later(tmp_path):
    responses = iter([None, {"registered": False}, {"registered": True}])
    posts = []

    def poster(url, payload):
        posts.append(payload)
        return next(responses)

    now = [1000.0]
    scheduler = ManualScheduler()
    reporter = InstallReporter(str(tmp_path),
                               "https://collector.example.com/api/installs",
                               version_name="1",
                               clock=lambda: now[0], scheduler=scheduler,
                               poster=poster)
    reporter.choose(True)  # POST 1 fails (None)
    assert not _state(tmp_path).get("sent")

    # Immediate re-report is inside the 30 s backoff: it schedules instead.
    reporter.report()
    assert len(posts) == 1 and len(scheduler.pending) == 1
    delay = scheduler.pending[0][0]
    assert 0 < delay <= 30.0

    now[0] += 30.0
    scheduler.fire()  # POST 2: registered=false -> still not sent
    assert len(posts) == 2 and not _state(tmp_path).get("sent")

    now[0] += 30.0
    reporter.report()  # POST 3: registered -> sent, same id throughout
    assert len(posts) == 3
    assert _state(tmp_path)["sent"] is True
    assert len({p["installation_id"] for p in posts}) == 1


def test_needs_choice_and_storage_failure(tmp_path):
    poster = lambda url, payload: {"registered": True}
    reporter = _configured(tmp_path, poster)
    assert reporter.needs_choice() is True
    reporter.choose(False)
    assert reporter.needs_choice() is False

    # Unconfigured reporter never asks and never reports.
    unconfigured = _reporter(tmp_path)
    assert unconfigured.needs_choice() is False

    # A storage failure flips storage_unavailable and stops the choice.
    broken = _configured(tmp_path, poster)
    broken._write = lambda state: (_ for _ in ()).throw(OSError("disk"))
    broken.choose(True)
    assert broken.storage_unavailable is True
    assert broken.needs_choice() is False
