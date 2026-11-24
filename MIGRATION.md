# Kotlin → Kivy/Python migration

Tracking document for migrating PayNet from Kotlin/Jetpack Compose to
Kivy/Python. Updated after every migrated feature. Source of truth for
what is done, what is verified, and what is not.

> **The Kotlin app has been removed from the repository.** The repo is
> Python-only. The last commit containing the Kotlin source (`app/`, Gradle
> build, Kotlin CI) is `de292ba`; every `Kotlin source` path below and every
> "Ported from app/…" header in `kivy/` refers to that tree, e.g.
> `git show de292ba:app/src/main/AndroidManifest.xml`.

## Guardrails (binding for the whole migration)

- **No git history rewrites.** New atomic commits only, one per completed
  feature, on the `kivy-migration` branch. `master` stays stable until the
  migration is complete and verified.
- **LICENSE, NOTICE and attribution headers stay intact.** The upstream
  Apache-2.0 copyright headers are preserved in ported files, with a
  "Ported from" line added.
- **Payment behavior is tested with mocks only.** No real USSD/UPI call is
  ever triggered from development or CI. Anything that only exists on a
  device (dialler hand-off, IVR, call audio, overlay window, SMS broadcast,
  camera) is listed under *Not verified from desktop* — never claimed as
  verified parity.
- **The app stays runnable throughout.** The Kivy app must launch
  (`python kivy/main.py`) and pass its test suite (`pytest kivy/tests`)
  after every commit.

## Audit of the existing app (Kotlin, 16.8k LOC main / 8.5k LOC tests)

Single-module Android app, no backend, no INTERNET permission. Compose UI,
Room + SQLCipher persistence, CameraX + ZXing scanning. See
`docs/ARCHITECTURE.md` for the full map. The load-bearing invariant:
**a payment is only ever marked SUCCESS by a confirming bank SMS, matched
to amount, inside an active payment window — never by call state.**

Feature inventory (Kotlin source → planned Python module):

| # | Feature | Kotlin source (main LOC) | Python target |
|---|---------|--------------------------|---------------|
| 1 | Payment input validation, UPI 123PAY dial-string builder, phone/currency utils, prompt timing | payment/Upi123CallStringBuilder.kt, PaymentInputValidator.kt, InvalidReasonMessages.kt, PaymentPromptTiming.kt, utils/{PhoneNumberUtils,PaymentPhoneInput,CurrencyFormat}.kt, constants/AppConstants.kt | paynet/payment/{call_string,validation,messages,prompt_timing}.py, paynet/utils/{phone,currency}.py, paynet/constants.py |
| 2 | App shell: Kivy app, navigation, theme tokens | ui/theme/{Color,Type,Theme,HomeColors,OnboardingColors,AccentTheme,PayNetViewTheme}.kt, PayNetApplication.kt, di/AppContainer.kt | paynet/app.py (incl. AppContainer), paynet/theme.py |
| 3 | SMS transaction parser (pure, per-bank corpus) | payment/sms/SmsTransactionParser.kt | paynet/sms/parser.py |
| 4 | Persistence: transactions, settings | data/{AppDatabase,Transaction,TransactionDao,TransactionStatus,PaymentStatus,PaymentDetails,UPIData,SettingsRepository,TestResults,DatabaseKeyManager,DatabaseEncryptionMigrator}.kt, repository/TransactionRepository.kt | paynet/db/{models,database,settings}.py, paynet/repository.py |
| 5 | Payment session state machine | payment/PaymentSessionManager.kt, states/PaymentState.kt, payment/{PaymentWindowObserver,QrWaitingState}.kt | paynet/payment/{session,state,window}.py |
| 6 | SMS ingestion pipeline + dedup + operation window | helpers/TransactionDetector.kt, receivers/{SimpleSMSReceiver,SmsIngestionPipeline,PaymentResultNotifier}.kt | paynet/sms/{detector,pipeline,receiver,notifier}.py |
| 7 | Telephony: call placement, call-state coordination, audio | managers/CallManager.kt, telephony/CallStateCoordinator.kt | paynet/telephony/{call_manager,coordinator}.py |
| 8 | Home dashboard screen | MainActivity.kt, MainScreenContent.kt, ui/home/{HomeDashboard,LegacyHomeDashboard,ModernHistoryPanel,HomeAppearance,HomeAppearancePreview}.kt, viewmodel/{MainViewModel,TransactionViewModel}.kt | paynet/ui/home.py, paynet/ui/home_legacy.py, paynet/viewmodels.py |
| 9 | Transaction history + detail dialog | ui/activities/{TransactionHistoryActivity,TransactionPresentation}.kt, ui/components/TransactionDetailDialog.kt | paynet/ui/history.py |
| 10 | Pay-contact flow + contact picker | PayContactContent.kt, ui/dialogs/ContactPickerDialog.kt | paynet/ui/pay_contact.py |
| 11 | QR scanner | features/qr_scanner/** | paynet/qr/{scanner,parser,analyzer}.py |
| 12 | Setup + onboarding + appearance setup | SetupActivity.kt, SetupAdvanceState.kt, helpers/{SetupHelper,OnboardingFlow,MainActivityHelper}.kt, ui/dialogs/OnboardingDialog(+Copy).kt, OnboardingPage.kt, AppearanceSetupActivity.kt | paynet/ui/{setup,onboarding,appearance}.py |
| 13 | Settings screens | ui/activities/Settings*.kt | paynet/ui/settings.py |
| 14 | Payment result screen + progress dialogs + notifications | ui/activities/PaymentResultActivity.kt, ui/dialogs/{UssdProgressDialog,Upi123ProgressDialog}.kt, managers/TransactionDialogManager.kt, ui/components/{PaymentPromptLayout,PaymentAnswerButton,SmsPermissionNotice}.kt | paynet/ui/result.py, paynet/ui/prompts.py |
| 15 | Call overlay service | services/{CallOverlayService,CallOverlayView,CallOverlayMessageMotion}.kt, utils/OverlayLogger.kt | paynet/overlay/service.py |
| 16 | Diagnostics: test-configuration screen, permissions, install metrics | TestConfigurationActivity.kt, helpers/TestConfigurationHelper.kt, managers/PermissionManager.kt, metrics/{InstallReporter,InstallCountActivity}.kt, utils/ContextExt.kt, helpers/MainActivityHelper.kt | paynet/ui/diagnostics.py, paynet/permissions.py, paynet/metrics.py |
| 17 | Android packaging: buildozer, manifest parity (permissions, SMS receiver, overlay service), CI | AndroidManifest.xml, build.gradle.kts (both at `de292ba`) | kivy/buildozer.spec, Android build CI job (Python CI already in .github/workflows/build.yml) |

## Decisions

- **Plain Kivy, no KivyMD.** The Compose UI is a custom dark violet theme,
  not stock Material; Kivy widgets + the ported theme tokens give exact
  control with fewer dependencies.
- **Kivy app lives in `kivy/`** (package `paynet`, entry `kivy/main.py`,
  tests `kivy/tests`). The Kotlin app was removed once features 1-16 were
  ported (see the note at the top).
- **sqlite3 (stdlib) replaces Room.** SQLCipher/Keystore at-rest encryption
  is a parity risk on the Python side — see *Parity risks*.
- **Android APIs via pyjnius** (dialer, telephony callbacks, SMS broadcast,
  contacts, camera, overlay window). CameraX + ZXing can be pulled in as
  Android dependencies through buildozer; ZXing decode stays the same library.
- **Coroutines → synchronous writes + threading.Timer.** The session
  manager's fire-and-forget coroutine writes become synchronous calls, so
  the pendingInsertJob-join invariant (a confirmation must never beat the
  PENDING insert) is satisfied by construction. The verification deadline
  is a threading.Timer; tests inject a manual scheduler. StateFlow/SharedFlow
  become value properties + listener lists. Claim-terminal-state-inside-lock
  before any store write is preserved exactly (RLock).
- **Unit tests are ported 1:1** where platform-independent (Compose
  `TextFieldValue` selection/saver mechanics are adapted to a small
  Python `TextValue` model).

## Parity risks

- At-rest DB encryption (SQLCipher + Android Keystore-wrapped key) has no
  drop-in Python equivalent on Android. Target: SQLCipher via a p4a recipe
  if viable; otherwise record the deviation explicitly before merge.
- `TYPE_APPLICATION_OVERLAY` window from a Python service is the least
  trodden p4a path; expect the overlay to be the hardest feature.
- Compose → Kivy is not pixel-identical. Preserved: layout structure,
  colors, copy, state, behavior. Not preserved: exact dp-level metrics of
  Compose animations.

## Not verified from desktop (mocks only — must be re-verified on device)

- USSD `*99#` session behavior and UPI 123PAY IVR DTMF flow.
- Actual call placement, call audio mode management, End-call via Telecom.
- SMS broadcast reception (`SimpleSMSReceiver`) and notification posting.
- Camera preview + QR decode, contact picker data.
- Overlay window draw/interaction during a live call.
- Keystore-wrapped DB key recovery paths.

## Status

| # | Feature | Status | Tests | Notes |
|---|---------|--------|-------|-------|
| 1 | Payment validation + dial-string + utils | ✅ Done | pytest (ported 1:1) | Desktop-verified |
| 2 | App shell + theme | ✅ Done | import smoke | UI placeholder only |
| 3 | SMS transaction parser | ✅ Done | pytest (full bank corpus + regex blocks, 1:1) | Desktop-verified; broadcast-receiver wiring is feature 6 |
| 4 | Persistence: transactions, settings | ✅ Done | pytest (DAO guards, mapping, settings) | Flow -> sync queries, SharedPreferences -> JSON prefs; SQLCipher parity pending (see Parity risks) |
| 5 | Payment session state machine | ✅ Done | pytest (27 session tests incl. both real-thread race tests, 1:1) | Coroutines -> synchronous store writes (join invariant satisfied by construction); watchdog = threading.Timer, manual scheduler in tests; StateFlow -> subscribe/listeners |
| 6 | SMS ingestion pipeline + dedup + operation window | ✅ Done | pytest (9 pipeline tests 1:1 + detector window/dedup/concurrency + receiver guards + notifier mapping) | Android bindings (PDU parsing, goAsync, LocalBroadcastManager, NotificationManager) are injected callables; pyjnius wiring is feature 17, unverified from desktop |
| 7 | Telephony: call placement, call-state coordination, audio | ✅ Done | pytest (8 coordinator 1:1 + 9 call-manager decision tests) | CallManager ported behind a PhonePlatform protocol; pyjnius platform binding is feature 17, unverified from desktop |
| 8 | Home dashboard screen (modern + classic legacy variants) | ✅ Done | pytest (4 home tests: sizing formulas, bank-name map, state transitions) + headless render verification (payments/empty/loading/error states) | Modern HomeDashboard + ModernHistoryPanel + brand card/tiles/FAB ported 1:1 (BoxWithConstraints formulas preserved); viewmodels + HomeAppearance landed in part 1; classic LegacyHomeDashboard variant ported in part 3 and render-verified (payments/empty/loading/error); rows top-pinned manually instead of LazyColumn scroll (Kivy nested ScrollView viewports do not translate reliably in this build); visual glyphs stand in for vector icons (arrow/QR/gear); loading state uses an ellipsis label instead of CircularProgressIndicator |
| 9 | Transaction history + detail dialog | ✅ Done | pytest (23 history tests: grouping, status labels, formats, states, search, detail/delete flow) + headless render verification (list/search/empty/detail/delete-confirm states) | TransactionHistoryActivity + TransactionDetailDialog + delete confirm ported 1:1; date grouping (Today/Yesterday/This Week/historical), search filter, status pills and Indian rupee grouping preserved; detail receipt opens from history rows and from home recent rows via viewmodel.selected_transaction; deviations: AnimatedVisibility search collapse is a height swap, snackbar is a plain bottom bar, ellipsis label instead of CircularProgressIndicator, glyphs for Material icons |
| 10 | Pay-contact flow + contact picker | ✅ Done | pytest (21 pay-contact tests: state validation, contact filtering, dialog behavior, initiator gates) + headless render verification (empty/filled/over-cap/picker/selected states) | PayContactContent + ContactPickerDialog + PermissionExplanationDialog + initiateTransfer/canInitiateTransfer/isTransferInputValid gates ported 1:1 (normalize/cap/canTransfer, digits-only 6-char amount, name-or-number contact filter, upi123Enabled gate -> setup callback, session begin with PENDING row); deviations: contact read permission gate and contacts provider are a ContactProvider protocol with an UnavailableContactProvider stub on desktop (device-only, unverified), the real IVR call is never placed from the desktop build (place_call injectable, None here — recorded device-only), TransactionDetector/CallOverlayService wiring is feature 12+, toast = bottom bar, ellipsis for spinner |
| 11 | QR scanner flow + UPI QR parser | ✅ Done | pytest (46 QR tests: parser corpus, analyzer latch/invert, controller flow/permissions/clipboard/session) + headless render verification (scanning/invalid/waiting/steps states) | QRCodeParser + QRCodeAnalyzer + QRScannerActivity flow ported 1:1 (strict upi:// + bare VPA with Android getQueryParameter semantics, amount/pn validation, normal-then-inverted decode, 2s duplicate latch, SOURCE_QR session begin with recipient fallback, sensitive VPA clipboard copy/wipe with owner token, dial-once guard + 1s delay, CALL_PHONE permission round-trip, invalid banner + rearm + 3.5s autohide, 3s error recovery, gallery pick/decode, session-state close watcher); deviations: camera preview, torch hardware, photo picker, real ZXing decode and the real USSD dial are device-only and unverified from desktop (decode_source/invert_source/dial/permission are injected callables), ellipsis label for ProgressBar, delayed swap for the instructions cross-fade, canvas-drawn glyphs for vector icons, dead revealQrAnswers/qrOutcomePanel not ported, camera executor/generation lifecycle folded into controller hooks |
| 12 | Setup + onboarding + appearance setup | ✅ Done | pytest (18 setup/onboarding tests ported from OnboardingFlowTest + SetupHelperContextTest + SetupSingleSimSelectionTest) + headless render verification (setup empty/filled/disclaimer-expanded, appearance choices, welcome) | SetupHelper + OnboardingFlow + SetupAdvanceState + OnboardingDialog(+Copy/Action/Progress/ConfirmationActions) + OnboardingPage + SetupScreen + AppearanceSetupActivity + HomeAppearancePreview ported 1:1 (bank/SIM catalogues, validators, context-change readiness invalidation, Jio-before-user-reported blocked-message ordering, appearance/welcome pref gates, settle-then-advance 600ms, startup routing appearance -> setup -> home, scan-to-pay gate wired into the QR scanner open); deviations: TestConfigurationActivity destination is feature 16 (setup completion and readiness gates route home until then, marked in app.py), phone-permission request leg of startQRScanning is device-only (feature 17), page-transition animations and TextAutoSize dropped, ExposedDropdownMenuBox -> Kivy Dropdown, M3 Checkbox -> canvas box, preview action glyphs omitted (colored shapes kept), warnIfVoiceSimMismatch is SubscriptionManager-bound and stays device-only/unverified |
| 13 | Settings screens | ✅ Done | pytest (12 settings tests ported from SettingsBankSourceTest + SettingsDataResetTest + viewmodel basics) + headless render verification (main, bank picker, clear-data, version sheets) + app-level navigation smoke | SettingsViewModel + SettingsState + resetSettingsData + SettingsActivity/Components/Sheets/Dialogs ported 1:1 (setup-bank-over-repository precedence, appearance design/color cycle rows saving HomeAppearance, bank/SIM pickers invalidating readiness on change, reset flow ordering history -> prefs -> setup with failure preserving state, version 1.0.0-sms from build.gradle.kts); deviations: runtime permission reads behind an injected provider (all False on desktop, device-only), InstallReporter row gated on an injectable predicate (metrics are feature 16), PrivacyActivity and GitHub link are injected no-op callbacks (platform wiring is feature 17), ModalBottomSheet -> bottom overlay layer, LazyColumn -> ScrollView |
| 14 | Payment result screen + progress dialogs + notifications | ✅ Done | pytest (40 tests covering the ported presentation/dialog rules; Kotlin ships no tests here beyond PaymentPromptTimingTest, already ported in feature 11) + headless render verification (success, failed, needs_review, unverified, outcome prompt, callback notice, ussd setup dialog) | PaymentResultActivity + UssdProgressDialog + Upi123ProgressDialog + TransactionDialogManager + PaymentPromptLayout + PaymentAnswerButton + SmsPermissionNotice ported 1:1 (status-driven styling where only explicit SUCCESS earns the accent/check look, bankReferenceOf timestamp-suffix strip, counterpartyLabelFor past-tense only on SUCCESS, recipient row precedence name -> phone -> UPI_123 detector fallback, staggered 24ms entry animations, 3s shortcut reveal, confirmation-option swap, dialog-failure toast fallback with session acknowledgement, awaiting-confirmation never acknowledging, saving state disabling answers at 0.5 alpha, prompt width min(window-48dp, 380dp)); deviations: immersive system-UI/back dispatch/overlay window typing are platform concerns (feature 17), SMS + notification permission requests behind injected callables (device-only), toast fallback behind an injected callable, notifications land with the service in feature 15; also fixes three latent Kivy layout bugs from features 12-13 found during render verification (OnboardingDialog body/close-glyph absolute positioning, empty content column default height, OnboardingPage fighting its ScrollView) |
| 15 | Call overlay service | ✅ Done | pytest (29 overlay tests: CallOverlayPresentationTest ported 1:1 - bind reset, connecting/in-call pacing milestones and ceiling, stop/restart rules, reduced-motion milestones, clamping, guidance timing - plus orchestration coverage for the watchdog, detection, retries, payment-state routing and terminate ordering) + headless render verification (connecting, in-call, muted, guidance) | CallOverlayService + CallOverlayView + CallOverlayMessageMotion + CallOverlayProgress + OverlayLogger ported 1:1 (40s watchdog re-arming in 10s steps max 3x only while the device is not Idle, duplicate-detection and missing-pending guards, overlay retry with 1/2/3s backoff then toast, permission gate with toast, session-driven results where Success vibrates and ends the call without a dialog, Failed/Cancelled route to the feature-14 TransactionDialogManager, result handled exactly once per service lifetime, terminate marks the session cancelled before any cleanup, volume pill only on successful lower, PIN guidance at 2.5s and auth guidance 16.5s later, pacing ceiling at 90% so the bar never declares completion); deviations: Android Service lifecycle/binder/WindowManager overlay window map to a plain object plus an in-app overlay host (feature 17 owns platform windows), vibration/overlay permission/toasts behind injected callables, animation frames computed from an injectable monotonic clock instead of ValueAnimator, CallOverlayMessageMotion reflow uses Kivy Animation |
| 16 | Diagnostics: test-configuration screen, permissions, install metrics | ✅ Done | pytest (29 tests: MainActivityReadinessTest + InstallReporterTest + InstallReceiptStateTest ported 1:1, plus TestConfigurationHelper flow, report/backoff/storage-failure and permission-group coverage) + headless render verification (initial, jio-unavailable, ussd progress/confirm, upi123 progress, consent, ready, install-count, install-count-saving) | TestConfigurationHelper + TestConfigurationScreen + PermissionConstants/PermissionManager + InstallReporter + InstallCountScreen + MainActivityHelper ported 1:1 (duplicate-dial guard, phone-permission gate before any test call, *99# 25s timeout -> configuration options, dismiss-from-X on confirmation = "Not yet", "It isn't working" sets the user-reported flag and retrying clears it, UPI123 call-end + 2s delay -> options, scan-deadline save/restore across recreate, skip/continue save results + set test_configuration_completed + navigate, canContinue/allTestsCompleted with the Jio/user-reported USSD waiver, readiness rails where QR needs ussdEnabled and transfer needs upi123Enabled, validation ahead of readiness ahead of RECEIVE_SMS -> phone -> overlay gates, invalidation re-checked on the same helper, InstallReporter endpoint rules https-only/debug-loopback/no-userinfo-query-fragment, consent/ID/sent receipt with atomic replace, 30s retry backoff, mark-sent only on registered=true, storage failure -> storageUnavailable and never blocks, InstallCount consent screen wired at startup and from Settings); deviations: the real *99#/UPI123 calls, ACTION_CALL intent, permission launcher, overlay-settings intent, warnIfVoiceSimMismatch and the metrics POST are device-only injected callables never triggered off-device (feature 17), BuildConfig endpoint maps to PAYNET_INSTALL_METRICS_URL (empty = unconfigured, as the Kotlin default), AtomicFile/noBackupFilesDir map to temp-then-rename in the data dir, the Compose 100ms state poll maps to a Kivy Clock interval, ContextExt's activity walk has no Kivy equivalent (not ported), row rebuilds instead of Compose recomposition, Kivy Widget.disabled dims the subtree so row enablement is a touch gate only |
| 17 | Remaining features | ⬜ Pending | | |

Test command: `cd kivy && python -m pytest tests -q`
Run command: `cd kivy && python main.py`
