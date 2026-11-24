# Security Policy

We handle UPI 123Pay payment flows, USSD dialing, and SMS parsing. Please treat security issues with appropriate care: **do not file public GitHub issues for vulnerabilities.**

## Supported versions

Security fixes land on the latest tagged release and on `master`. Older releases
are not backported — update to the newest release.

| Version               | Supported |
|-----------------------|-----------|
| 1.0.x                 | ✅        |
| `master` (unreleased) | ✅        |
| < 1.0                 | ❌ pre-release, never distributed |

## Verifying you have a genuine build

We'll be sharing an updated version of PayNet on this repository's [GitHub Releases](https://github.com/rajarshidattapy/paynet/releases).
Use that page for official APK downloads when available. In the meantime,
you can run from source with [Running it](../README.md#running-it).

The codebase is now Python/Kivy. Its Android packaging exists in `app/` but
has never been built or verified on a device, and no APK of it has been
published.

The signing certificate is the trust anchor. Fake UPI apps are common in
India, and an APK claiming to be PayNet can come from anywhere. No signed
PayNet APK has been published yet, so **any PayNet APK you find in the wild
today is not official** — run from source instead.

The release signing certificate's SHA-256 fingerprint will be committed here
ahead of the first APK release, so it cannot be back-dated later. When it
lands, check any APK against it:

```bash
apksigner verify --print-certs paynet-vX.Y.Z.apk
```

Compare against the fingerprint committed **here**, not against the release
notes — release notes are written by whoever published the release, so checking
them against themselves proves nothing.

A change to the fingerprint in a future version means the signing key changed.
That is not normal; ask before installing.

Running from source remains fully supported and needs none of this — see
[Running it](../README.md#running-it).

## Reporting a vulnerability

Email **`rayan05rio@gmail.com`** with the subject line:

> `PayNet UPI — Security report — <one-line summary>`

Please include:

1. A clear description of the issue and the affected component (file path, screen, or flow).
2. Steps to reproduce — against the desktop build (`cd app && python main.py`), or as a failing test under `app/tests`.
3. Impact — what an attacker can read, modify, or trigger.
4. Suggested fix, if you have one.
5. Your contact info if you want credit in the eventual fix commit.

If the issue involves a leaked secret in the codebase or git history, include the commit SHA.

## Disclosure timeline

- **Within 72 hours** — acknowledgement that the report was received.
- **Within 14 days** — initial assessment shared with the reporter.
- **Within 90 days** — fix landed in `master` and credit posted (if requested), or a written explanation of why disclosure should be delayed.

Industry-standard 90-day window. If a fix lands sooner, credit is posted sooner.

## Scope

In scope:

- The app source under `app/paynet/` and its entry point `app/main.py`.
- The pinned dependency list (`app/requirements.txt`) and the Android packaging configuration (`app/buildozer.spec`, `app/p4a/hook.py`, `app/android-src/`).
- The sqlite schema (`app/paynet/db/database.py`) and the JSON preference files the app writes.
- The USSD dialer flow, SMS parser and ingestion pipeline, and call-overlay service.

Out of scope:

- Issues with third-party Android system APIs we use (`TelecomManager`, `SmsManager`, etc.) — those belong to Google/AOSP.
- Issues in Kivy, the Python runtime, or other upstream dependencies themselves — report those upstream (a PayNet-specific misuse of them is in scope).
- Issues with the user's bank or UPI provider — those belong to the bank/NPCI.
- Theoretical issues that require an already-rooted device.

## Safe harbour

Researchers acting in good faith, sticking to the disclosure timeline above and not exfiltrating real user data, will not be pursued legally for the testing itself.

## Data handling & threat model

What the app stores, where, and for how long. Everything is written to
Kivy's per-user data directory for the app (`App.user_data_dir`):

| Data | Where | Lifetime | Leaves the device? |
|------|-------|----------|--------------------|
| Transaction rows (amount, status, bank, bank ref, counterparty name/number/UPI ID, privacy-safe summary) | sqlite3 file `paynet.db` — **plaintext, not encrypted at rest** | Until the user deletes them (individually, or via Settings' clear-data) or removes the data directory | Never sent by the app. **Not excluded from backups** — the Android backup exclusions of the Kotlin app have not been recreated (packaging is pending), and on desktop the directory is covered by whatever backs up the user's profile |
| Raw bank SMS bodies | **Not stored** — only a summary built from parsed fields | — | The verbatim SMS stays in the user's SMS inbox app only |
| Active payment-operation window (expected amount, recipient number, session id, start time) | `TransactionDetector.json` | Cleared when a confirming SMS consumes it, or when it is next checked after its ~10.5-minute life | Never sent by the app |
| Settings, setup choices, test results (bank, SIM, appearance, readiness flags) | `PayNetPrefs.json`, `paynet_settings.json`, `paynet_test_results.json` | Until the data directory is removed; Settings' clear-data wipes the settings and setup choices | Never sent by the app |
| Install-count receipt (consent choice, random installation ID, sent flag) | `install-receipt.json` | Until the data directory is removed | Only with explicit consent **and** a configured collector URL — and the HTTP request is not implemented in the current build, so today nothing is sent |
| UPI PIN | **Never seen by the app** — entered into the bank's IVR/dialer flow | — | — |

Design rules the code enforces:

- **No payment-path networking.** None of the payment, SMS, telephony or storage code opens a network connection. The only network feature is the opt-in install count above. (The Kotlin app's offline release builds also dropped the `INTERNET` permission entirely; `app/buildozer.spec` declares `INTERNET` and `ACCESS_NETWORK_STATE` for the install count, so that guarantee does not exist in the Python build.)
- **`READ_SMS` is not requested.** The design receives incoming SMS (`RECEIVE_SMS`) while a payment operation is active and never reads the inbox. The Java receiver (`app/android-src/`) is unverified on a device; nothing in the code reads an inbox.
- **SMS are only inspected inside an explicit payment window** — a ~10-minute operation (a 10-minute verification deadline plus a 30-second grace margin) started when the user initiates a transfer; outside it, `SimpleSMSReceiver.handle_sms` drops messages before parsing. Bank matching itself is deliberately permissive keyword matching (field-proven against real bank templates), so the operation window — not sender authentication — is the primary control.
- **Stored summaries are built constructively** from parsed fields (amount, direction or failure, bank — `build_excerpt` in `app/paynet/sms/parser.py`), so account numbers and balances in message prose can never reach the database.
- **A confirmation can only land on a PENDING row.** The SQL that applies a bank confirmation is guarded by status, so an SMS arriving after a cancel cannot flip the cancelled row to SUCCESS.
- **There is one SMS ingestion path.** The Kotlin app's notification-listener fallback was removed as dead code before the port and was not carried over, so nothing in the app reads notification content from other apps.
- CI rejects log statements that interpolate SMS bodies in `app/paynet/payment`, `app/paynet/sms` and `app/paynet/overlay`.

## Known deferred issues

Named here so nobody mistakes a gap for a protection:

- **The transaction database is not encrypted at rest.** The Kotlin app used
  SQLCipher with a key wrapped by a non-exportable Android Keystore key. The
  Python port uses stdlib `sqlite3` with no encryption; SQLCipher parity is
  an open item.
  Anyone who can read the app's data directory can read the payment history.
- **Device-only protections are unverified.** Permission gates
  (`RECEIVE_SMS`, phone, overlay) before a payment, the SMS broadcast
  receiver, the dual-SIM mismatch warning, and the overlay window are
  injected callables that are `None` or stubbed off-device. Their logic is
  unit-tested; the Android bindings in `app/paynet/platform/android.py` and
  the Java receiver have never run on a device. The in-call overlay is not
  started by any payment flow yet, and the pay-contact flow does not check
  `RECEIVE_SMS` or overlay permission before dialling.
- **Logging is not stripped from any build.** The Kotlin release builds
  removed all logging at compile time. The Python code uses standard
  `logging` loggers with nothing equivalent; the payment and SMS modules log
  at debug level and never the message body (CI-enforced), but whatever log
  sink the runtime configures will receive what is logged.

If you spot something else with security implications, please report it.
