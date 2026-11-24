# PayNet architecture

PayNet is a Python/Kivy app that puts a smartphone UI on top of two offline
UPI rails — `*99#` USSD and UPI 123Pay IVR — and confirms payment outcomes
by reading the bank's confirmation SMS locally. There is no backend and no
telemetry. All code lives in [`kivy/`](../kivy): the `paynet` package, the
entry point [`kivy/main.py`](../kivy/main.py), and the test suite in
[`kivy/tests`](../kivy/tests). This document is the map: how the pieces fit,
where the load-bearing invariants live, and which known simplifications and
gaps are deliberate.

The code is a feature-by-feature port of an earlier Kotlin/Jetpack Compose
app (last present at commit `de292ba`). [MIGRATION.md](../MIGRATION.md) is
the source of truth for what has been ported, what is verified, and what is
not. Two gaps shape everything below:

- **Android packaging is not done yet** (feature 17: buildozer, manifest,
  pyjnius bindings). Every device-only surface — dialling, call-state
  callbacks, SMS broadcast reception, notifications, camera/ZXing decode,
  contacts, the overlay window, vibration, permission prompts — sits behind
  an injected callable or a small protocol class. Off-device those are
  `None` or stubs, so the desktop build never dials and never receives an
  SMS. The logic around them is unit-tested; the bindings themselves are
  **unverified**.
- **At-rest encryption is not carried over.** The transaction database is
  plain sqlite3 (see [Persistence](#persistence)).

## The one invariant that matters

**A payment is only ever marked SUCCESS by a confirming bank SMS — never by
call state or call duration.** Everything below serves this. A dialed call
that connects and ends "normally" proves nothing; only the bank's own
confirmation SMS, matched to the amount that was sent, promotes a payment to
SUCCESS. When no SMS arrives before the deadline, the attempt is discarded
and nothing is shown — an outcome the bank never confirmed is not one this
app can report on, and it is never silently assumed either way.

## Composition root

[`AppContainer`](../kivy/paynet/app.py) is the manual, framework-free
composition root, constructed once by `PayNetApp.build()` with Kivy's
per-user data directory. It constructs and holds the process-scoped graph:

```
AppContainer (kivy/paynet/app.py)
├── prefs, settings, test_results      (JSON-file preferences, paynet/db/settings.py)
├── database → repository              (sqlite3 Database → TransactionRepository)
├── main_view_model, transaction_view_model
├── call_coordinator                   (the ONE telephony listener; telephony=None off-device)
├── payment_session_manager            (the ONLY writer of payment state)
│       └── store = repository         (implements PaymentTransactionStore)
├── transaction_detector               (the SMS operation window + dedup)
└── install_reporter                   (opt-in install count; see SECURITY.md)
```

Screens and helpers reach these through the app instance. DI is hand-wired
on purpose: the graph is small, and for a payments app, construction a
reader can follow by eye beats framework indirection.

Not everything that has been ported is wired into the container yet.
`SimpleSMSReceiver`, the ingestion pipeline, `PaymentWindowObserver`,
`CallOverlayService` and `PaymentResultScreen` exist and are tested, but
nothing in `AppContainer` constructs them today — their entry points are
platform events (an SMS broadcast, a call going off-hook) that only exist
once the Android bindings land.

## Payment lifecycle state machine

[`PaymentSessionManager`](../kivy/paynet/payment/session.py) is the single
writer of payment state and the most carefully-built part of the app. It
takes its dependencies as protocols (`PaymentTransactionStore`, plus a call
coordinator exposing `acquire`/`release`/`add_session_listener`), an
injectable clock, and an injectable watchdog factory, which is what makes it
fully unit-testable without a device (see
[`tests/test_payment_session.py`](../kivy/tests/test_payment_session.py)).
States are the dataclasses in
[`paynet/payment/state.py`](../kivy/paynet/payment/state.py).

```
begin(phone, amount)          [QR: begin("", amount, upi_id, source=QR)]
   │  writes a PENDING row BEFORE anything is dialed, so a process death
   │  mid-call still leaves a record of the attempt
   ▼
Initiating ──Started──▶ InProgress ──Ended──▶ WaitingForVerification
   │                        │  (short call <5s ⇒ Cancelled, never SUCCESS)     │
   │                        │                                                   │
   └── dial failed /        └───────────── confirming bank SMS ────────────────┤
       call never started              (on_sms_confirmed)                       │
              │                                                                 ▼
              ▼                              ┌── amount matches ⇒ Success ──────┤
           Cancelled                         ├── amount mismatch ⇒ dropped,     │
       (PaymentWindowObserver also           │   window stays open for the      │
        closes the SMS window, so a          │   real confirmation              │
        later debit can't be adopted         └── failure keyword ⇒ Failed       │
        onto the cancelled row)                                                 │
   no SMS before the 10-minute deadline ⇒ Timeout, and the PENDING row is DELETED
                                             │
                    Nothing is surfaced: a payment the bank never confirmed
                    leaves no record. The SMS window outlives the deadline by
                    30s, so a late-but-genuine confirmation still lands — with
                    no row to adopt it is saved as a standalone transaction.
```

`Started`/`Ended` are the `CallSessionEvent`s emitted by the call-state
coordinator (OFFHOOK, then back to idle). A bank SMS that reports the
payment as needing review moves the session to `NeedsReview` instead of
`Success`, and an incoming CREDIT never confirms a session (a session is
always an outgoing DEBIT).

The Kotlin original ran its writes as fire-and-forget coroutines and had
every terminal transition join the pending-insert job first. The port
writes **synchronously**: `begin()` does not return until the PENDING row
exists, so a confirmation can never beat the insert by construction. What
carries over exactly is *claim first, write second*: the terminal state is
claimed inside one `threading.RLock`, and only the caller that claimed it
writes to the store, so a cancel landing at the same instant as the bank's
SMS can never leave history contradicting the screen. The verification
deadline is a `threading.Timer`; tests inject a manual watchdog.

A new `begin()` supersedes any session still in flight rather than being
refused, discarding the superseded PENDING row. Stale PENDING rows left by
a killed process are discarded by `delete_stale_pending` at the start of
every `begin()`; `reconcile_stale_pending()` exists for an app-start sweep
but is not yet called from `AppContainer`. If the process died mid-payment
and the confirming SMS arrives after restart, the ingestion pipeline
*reattaches* it: the session txn id is stored in the operation window by
`TransactionDetector.start_operation(session_txn_id=…)`, and a
no-live-session confirmation updates that still-PENDING row instead of
inserting a duplicate. Adoption is guarded to PENDING rows in SQL
(`Database.confirm_transaction`), so a confirmation can never rewrite a row
the user already cancelled. The QR flow
([`QRScannerController`](../kivy/paynet/qr/scanner.py)) runs through the
same session lifecycle and opens the operation window itself; the
pay-contact flow ([`TransferInitiator`](../kivy/paynet/payment/initiate.py))
opens the session, but its operation-window start and the IVR call are
device-only and not wired yet.

## SMS ingestion — one path, one parser

The confirmation SMS is money-outcome truth, so its handling is the second
most careful area.

```
                 ┌─────────────────────────────┐
  bank SMS ─────▶│ SimpleSMSReceiver           │  handle_sms(sender, body)
                 │ (RECEIVE_SMS)               │  platform binding: feature 17
                 └──────────────┬──────────────┘
                                │
                 should_process_sms() + try_claim_sms()
                                │
                                ▼
                        pipeline.ingest()
                                │
                  TransactionDetector.process_sms()
                                │
                        parser.parse()   ← PURE, platform-free, tested
                                            │
                     ┌──────────────────────┴───────────────────────┐
                     ▼                                               ▼
          active session? update its row              no session (QR/process died)?
          via PaymentSessionManager.on_sms_confirmed   adopt the window's PENDING row,
                                                       else insert a fresh row
                     └──────────────────┬──────────────────────────┘
                                        ▼
                  notifier(result), then open_result(result)
```

- [`paynet/sms/parser.py`](../kivy/paynet/sms/parser.py) holds all the
  bank-SMS matching logic — pure, platform-free (it takes a clock and a
  random-suffix provider as parameters), and tested against a per-bank
  corpus. [`TransactionDetector`](../kivy/paynet/sms/detector.py) is the
  stateful shell around it: the prefs-backed *operation window* (only SMS
  arriving while a payment is in flight are eligible; sized to the
  verification deadline plus a 30-second grace margin, so a slow bank SMS is
  never dropped here while the session still awaits it) and the dedup that
  stops a redelivered SMS broadcast from double-processing one message.
- **Dedup** is `try_claim_sms` (a body-only normalized-key claim, held for
  60 seconds) plus `process_sms` re-checking the operation window under the
  detector's lock.
- [`paynet/sms/pipeline.py`](../kivy/paynet/sms/pipeline.py) is the single
  path from a claimed SMS to an outcome — parsing, session confirmation or
  orphaned-row reattach, persistence, the published events, the result
  notification, and the result-screen launch. Its Android collaborators
  (broadcasts, the notification post, the result-screen launch) are injected
  callables, so tests drive the exact production function (see
  [TESTING.md](TESTING.md)).
- [`SimpleSMSReceiver`](../kivy/paynet/sms/receiver.py) ports only the guard
  logic (blank body, no open window, already claimed). Assembling a message
  from its PDUs and keeping the process alive while it is handled are the
  Android `BroadcastReceiver` binding, which is feature 17.
- The Kotlin app once had a second ingestion path, a
  `NotificationListenerService` fallback; it was removed before the port as
  dead code and has no Python counterpart. `RECEIVE_SMS` is the only planned
  SMS ingestion path.

## Telephony and the call overlay

[`CallStateCoordinator`](../kivy/paynet/telephony/coordinator.py) is the
single app-wide call-state listener; `PaymentSessionManager` consumes its
session events. It talks to the device through a `TelephonyAdapter`
protocol — `None` in `AppContainer` today, so off-device it only moves when
driven directly (which is how the tests drive it).
[`CallManager`](../kivy/paynet/telephony/call_manager.py) places the actual
call and manages call audio behind a `PhonePlatform` protocol; the DTMF
123Pay string is built and validated by the pure, tested
[`call_string.build()`](../kivy/paynet/payment/call_string.py).
[`CallOverlayService`](../kivy/paynet/overlay/service.py) drives the
in-call guidance UI ([`CallOverlayView`](../kivy/paynet/overlay/view.py))
and mirrors `PaymentState` into result dialogs. Its watchdog and the user
"End call" path notify the session **before** any best-effort UI/audio
cleanup, so an exception in that cleanup can't skip it. On Android the
overlay was a `TYPE_APPLICATION_OVERLAY` window; the port renders it through
an injected overlay host, and drawing it over the dialer from a Python
service is listed as the hardest open parity risk in MIGRATION.md.

## UI

Screens are plain Kivy widgets (no KivyMD, no `.kv` files), assembled in
`PayNetApp.build()` on a `ScreenManager`: home (modern
[`HomeScreen`](../kivy/paynet/ui/home.py) or classic
[`LegacyHomeScreen`](../kivy/paynet/ui/home_legacy.py), chosen by the saved
appearance), setup, appearance, settings, diagnostics (test configuration),
install count, history, and a QR scanner screen added on demand. Dialogs,
receipts and toasts are layered on a root `FloatLayout` above the screen
manager, because `ScreenManager` only accepts `Screen` children.

State lives in small view models
([`paynet/viewmodels.py`](../kivy/paynet/viewmodels.py): `MainViewModel`,
`TransactionViewModel`) and in plain-Python helpers kept apart from the
widgets (`SetupHelper` in [`paynet/setup.py`](../kivy/paynet/setup.py),
`SettingsViewModel` in [`paynet/settings.py`](../kivy/paynet/settings.py),
`TestConfigurationHelper` in
[`paynet/ui/diagnostics.py`](../kivy/paynet/ui/diagnostics.py),
`QRScannerController` in [`paynet/qr/scanner.py`](../kivy/paynet/qr/scanner.py)).
Kotlin's `StateFlow` became observable values with `subscribe()`; widgets
are updated from subscriptions through `Clock.schedule_once`, so changes
land on Kivy's main thread. Keeping logic out of the widgets is what lets
most of the UI rules run under pytest without opening a window.

Colors have a single source of truth: the tokens in
[`paynet/theme.py`](../kivy/paynet/theme.py), with
`status_color(status)` mapping a transaction status to its color
everywhere. User-visible copy is held as module-level string constants
beside the code that shows it (ported from the Android `strings.xml`
values); there is no central strings file and no automated gate against
inline colors or strings.

Kivy is not pixel-identical to Compose: layout, colors, copy, state and
behavior are preserved; exact animation metrics and some vector icons are
not (MIGRATION.md lists the per-screen deviations).

## Persistence

**Local-only, and not encrypted at rest.** Transactions live in a stdlib
`sqlite3` database ([`paynet/db/database.py`](../kivy/paynet/db/database.py))
at `paynet.db` in Kivy's per-user data directory. The Kotlin app used Room
with SQLCipher and an Android-Keystore-wrapped key; that has no drop-in
Python equivalent, and SQLCipher parity is an open item in MIGRATION.md's
*Parity risks*. Until it lands, anyone who can read the app's data
directory can read the payment history.

`Database` wraps one connection behind a `threading.RLock`, and its SQL
mirrors the Kotlin DAO one to one, including the lifecycle guards: a
confirmation lands only on a PENDING row, `transition_status` only moves a
row out of the expected status, and stale PENDING rows are discarded past
their deadline. Queries are synchronous and return lists; the UI re-queries
on demand. The schema is created with `CREATE TABLE IF NOT EXISTS` and has
**no version number and no migrations** — the next schema change must add
both, rather than silently diverging from rows already on disk. Data from
the Kotlin app's database is not imported.

The raw SMS body is never persisted — only a constructively-built,
privacy-safe excerpt from extracted fields (`build_excerpt` in
`paynet/sms/parser.py`). A CI grep gate blocks logging statements that
interpolate SMS bodies in `paynet/payment`, `paynet/sms` and
`paynet/overlay`.

Preferences replace Android `SharedPreferences` with small JSON files in the
same data directory (`PrefsStore`, written temp-file-then-rename):
`PayNetPrefs.json`, `paynet_settings.json`, `paynet_test_results.json`, the
operation window in `TransactionDetector.json`, and the install-count
receipt `install-receipt.json`.

## Platform components (pending packaging)

There is no Android manifest yet. The Kotlin manifest (see `git show
de292ba:app/src/main/AndroidManifest.xml`) is the reference packaging must
reproduce:

- **Activities → screens.** The Kotlin activities map to the Kivy screens
  above; there is a single Kivy activity on Android.
- **Service**: `CallOverlayService`.
- **Receiver**: `SimpleSMSReceiver` (priority-999, guarded by
  `BROADCAST_SMS`).
- **Debug only**: the Kotlin `DebugSmsInjectionReceiver` was not ported.

Permissions in the Kotlin build were payment-scoped: `CALL_PHONE`,
`READ_PHONE_STATE`, `ANSWER_PHONE_CALLS` (the overlay's End-call button),
`RECEIVE_SMS` (never `READ_SMS` — the inbox is never read), `CAMERA`,
`READ_CONTACTS`, `SYSTEM_ALERT_WINDOW`, `POST_NOTIFICATIONS`, `VIBRATE`, and
`MODIFY_AUDIO_SETTINGS`, with no location and no storage. The default Kotlin
manifest also declared `INTERNET` and `ACCESS_NETWORK_STATE`, used only by
the optional install-count receipt and stripped from releases built without
a collector URL. The runtime permission groups the app requests are in
[`paynet/permissions.py`](../kivy/paynet/permissions.py).

## Threat model & trust boundaries

See [SECURITY.md](SECURITY.md) for the full disclosure policy and threat
table. In short: the app triggers the dialer and reads confirmation SMS
locally; the UPI PIN is entered directly into the bank's IVR/dialer and is
never seen by PayNet; no accessibility service is used, so the app cannot
read the screen or other apps.

## Known deliberate simplifications

Honest about what isn't consolidated, and why:

- **`CallManager` is not app-scoped.** In the Kotlin app it was instantiated
  per caller (main flow, test screen, overlay service), and the legacy
  generic call path used its own per-call listener rather than the
  app-scoped `CallStateCoordinator`. The port keeps the same shape: no
  `CallManager` is held by `AppContainer`, and the diagnostics screen's test
  dial is an injected callable.
- **The port is synchronous where Kotlin used coroutines.** Store writes run
  on the calling thread; there is no background I/O dispatcher. That keeps
  the claim-then-write invariants simple, at the cost of sqlite writes on
  whatever thread delivers the event.
- The **permissive SMS matcher** is intentional — banks phrase confirmations
  inconsistently, and the downstream tiers (a debit with a mismatched amount
  is dropped outright — it isn't this payment's confirmation, and the
  operation window stays open for the real one; `Failed` on a failure
  keyword) are the safety net that keeps permissiveness from ever producing
  a false SUCCESS. It is permissive, not naive: body
  keywords match on word boundaries (with "YES"/"BOB" requiring the full bank
  phrase so promo SMS can't enter the pipeline), amount comparison is
  paise-exact, and extraction skips balance figures ("Avl Bal Rs …") in
  favour of the transaction amount. Growing the test corpus is the guardrail.
  Direction is read debit-first: many banks narrate both sides of one payment
  ("A/c XX556 debited for Rs 500; KIRANA STORE credited"), and taking such a
  body for an incoming credit would make the pipeline drop our own
  confirmation as unrelated.
