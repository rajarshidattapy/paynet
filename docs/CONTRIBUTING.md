# Contributing to PayNet

Thanks for your interest in contributing. This guide covers everything you need to get a development build running and to submit a change.

PayNet is a Python/Kivy app. It was ported from an earlier Kotlin/Jetpack Compose app, and [MIGRATION.md](../MIGRATION.md) tracks what has been ported, what is verified, and what is still pending — read its Status table before starting on anything that touches the phone, SMS, camera or overlay.

## Prerequisites

- **Python 3.11** (matches CI)
- The pinned dependencies in [`kivy/requirements.txt`](../kivy/requirements.txt) — Kivy and pytest
- On a headless Linux box, `xvfb-run` for the test suite (modules that import Kivy widgets need a display; CI uses the same)

There is no Android build yet. Packaging (buildozer, the Android manifest, and the pyjnius bindings for dialling, call state, SMS reception, notifications, camera and the overlay window) is feature 17 in MIGRATION.md and still pending. Today the app runs as a desktop Kivy app; every device-only action is an injected callable that is `None` or a stub off-device, so **the desktop build never dials, never sends a payment, and never receives an SMS.**

## First-time setup

```bash
git clone <repo-url>
cd paynet
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -r kivy/requirements.txt
```

`.venv/` is gitignored. No other local configuration is needed.

## Run & test

```bash
cd kivy
python main.py                   # launch the desktop app
python -m pytest tests -q        # run the test suite
```

Tests live in `kivy/tests/`, one file per ported area — for example `test_sms_parser.py`, `test_sms_regex.py`, `test_sms_pipeline.py`, `test_sms_receiver_notifier.py`, `test_payment_session.py`, `test_payment_state.py`, `test_payment_window.py`, `test_call_string.py`, `test_validation.py`, `test_call_state_coordinator.py`, `test_call_manager.py`, `test_database.py`, `test_models.py`, `test_qr_scanner.py`, `test_overlay.py`, `test_currency.py`, `test_phone.py`, plus screen-logic suites such as `test_history.py`, `test_result_prompts.py` and `test_setup_onboarding.py`. There are no device or emulator tests at present — see [TESTING.md](TESTING.md) Layer 2 for why, and what must come back with Android packaging. CI runs the suite on every push, so keep it green and add coverage for new logic where it makes sense. See [TESTING.md](TESTING.md) for the full verification story, including how to replay a bank SMS through the live ingestion pipeline without a real bank.

For visual changes, the dev-only `kivy/render_*.py` scripts build a single screen in a fixed-size window and save a screenshot (e.g. `python render_history.py search`); see [TESTING.md](TESTING.md).

### Adding a bank SMS template

The SMS parser is only as good as its corpus of real bank confirmation formats, and every bank's template is different — new samples are one of the most valuable contributions.

1. Take a real confirmation SMS from your bank and **redact it**: replace account digits with `**1234`-style masks, real names with placeholders (`KIRANA STORE`, `Rahul Sharma`), and reference numbers with obviously fake ones (`123456789012`). Keep the exact wording, punctuation, and field order — that's what the parser matches on.
2. Note the sender ID it arrived from (e.g. `VK-HDFCBK`) — DLT sender codes matter for bank detection.
3. Add it as a `BankCase(bank, sender, body, amount)` entry next to the existing samples in `BANK_CORPUS` in [`kivy/tests/test_sms_parser.py`](../kivy/tests/test_sms_parser.py) (failure templates have their own cases further down that file) and run `python -m pytest tests -q` from `kivy/`. If the parser mishandles it, file an issue with the redacted SMS and sender ID instead — that alone is a useful bug report.

## Project layout

```
kivy/
├── main.py                # entry point (PayNetApp().run())
├── requirements.txt       # pinned Kivy + pytest
├── pytest.ini
├── render_*.py            # dev-only headless screen renders
├── tests/                 # pytest suite
└── paynet/
    ├── app.py             # PayNetApp + AppContainer (composition root, navigation)
    ├── constants.py, status.py, theme.py
    ├── db/                # sqlite3 Database, Transaction models, JSON prefs/settings
    ├── repository.py      # TransactionRepository
    ├── payment/           # PaymentSessionManager, states, validation, 123Pay dial string
    ├── sms/               # parser, TransactionDetector, ingestion pipeline, receiver, notifier
    ├── telephony/         # CallStateCoordinator, CallManager
    ├── overlay/           # call overlay service + view
    ├── qr/                # UPI QR parser, analyzer, scanner controller
    ├── ui/                # Kivy screens and dialogs
    ├── utils/             # currency, dates, phone helpers
    └── setup.py, onboarding.py, settings.py, permissions.py, metrics.py, viewmodels.py
```

`paynet/setup.py` is the setup-screen logic, not a packaging script.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the pieces fit — the payment state machine, the SMS-ingestion pipeline, the composition root, and the deliberate simplifications and known gaps.

## Branching

- `master` — protected; only PRs land here.
- `feat/<short-name>` — new features
- `fix/<short-name>` — bug fixes
- `chore/<short-name>` — refactors, build/CI, deps

## Pull requests

Before opening a PR:

1. `cd kivy && python -m pytest tests -q` must pass.
2. `python main.py` must still launch.
3. If your change touches UI, attach a screenshot or short clip (a `render_*.py` screenshot is fine).
4. Link any related issue (`Closes #123`).
5. Keep the diff focused — one logical change per PR.

Never trigger a real USSD or UPI call from development or CI. Payment behavior is tested with fakes only; anything that only exists on a device is recorded as unverified, not claimed as working.

CI runs on every push and PR. A green run is required before merge.

## Code style

- 4-space indentation, UTF-8, LF line endings and a final newline — captured in the repo-root `.editorconfig`, which most editors respect automatically. No linter or formatter is configured; follow the style of the surrounding code.
- Never log raw SMS bodies. CI greps `kivy/paynet/payment`, `kivy/paynet/sms` and `kivy/paynet/overlay` for logging calls that interpolate a message body and fails the build if it finds one.
- **Every new `.py` file needs the licence header** — the first two lines:
  ```python
  # SPDX-License-Identifier: Apache-2.0
  # Copyright 2026 Flowpay
  ```
  The repo-root `LICENSE` doesn't travel with a file someone copies out, so per-file SPDX is what licence scanners actually read. Files ported from the Kotlin app also carry a `# Ported from app/...` line naming the original (that tree is at commit `de292ba`); keep it when editing them.

## Good first contributions

If you're looking for a place to start:

- **Add a bank SMS template** to the parser corpus (see "Adding a bank SMS template" above) — the single most valuable contribution, and low-risk.
- **Close a recorded UI deviation** — MIGRATION.md's Status table lists, screen by screen, where the Kivy port differs from the original (for example, ellipsis labels standing in for progress spinners). Closing one, with a before/after render, is a scoped task.
- **Improve a `docs/` page** — a clearer FAQ answer, a diagram, a fixed link.
- **Reduce a god-file** — `paynet/ui/diagnostics.py`, `paynet/ui/history.py` and `paynet/ui/home.py` are large; extracting a self-contained widget or helper (with no behavior change) is a good scoped task.
- **Report a carrier/USSD quirk** — the bug template asks for carrier and SIM; a well-documented report is itself a contribution.

## Filing issues

Use the templates under [.github/ISSUE_TEMPLATE](../.github/ISSUE_TEMPLATE) when opening an issue. For security reports, see [SECURITY.md](SECURITY.md) — do not file public issues for vulnerabilities.

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](../LICENSE).
