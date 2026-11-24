# Kotlin → Kivy/Python migration

Tracking document for migrating PayNet from Kotlin/Jetpack Compose to
Kivy/Python. Updated after every migrated feature. Source of truth for
what is done, what is verified, and what is not.

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
- **The app stays runnable throughout.** The Kotlin app is untouched on
  this branch; the Kivy app must launch (`python kivy/main.py`) and pass
  its test suite (`pytest kivy/tests`) after every commit.

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
| 2 | App shell: Kivy app, navigation, theme tokens | ui/theme/{Color,Type,Theme,HomeColors,OnboardingColors,AccentTheme,PayNetViewTheme}.kt, PayNetApplication.kt, di/AppContainer.kt | paynet/app.py, paynet/theme.py, paynet/container.py |
| 3 | SMS transaction parser (pure, per-bank corpus) | payment/sms/SmsTransactionParser.kt | paynet/sms/parser.py |
| 4 | Persistence: transactions, settings | data/{AppDatabase,Transaction,TransactionDao,TransactionStatus,PaymentStatus,PaymentDetails,UPIData,SettingsRepository,TestResults,DatabaseKeyManager,DatabaseEncryptionMigrator}.kt, repository/TransactionRepository.kt | paynet/db/{models,database,settings}.py, paynet/repository.py |
| 5 | Payment session state machine | payment/PaymentSessionManager.kt, states/PaymentState.kt, payment/{PaymentWindowObserver,QrWaitingState}.kt | paynet/payment/{session,state,window}.py |
| 6 | SMS ingestion pipeline + dedup + operation window | helpers/TransactionDetector.kt, receivers/{SimpleSMSReceiver,SmsIngestionPipeline,PaymentResultNotifier}.kt | paynet/sms/{detector,pipeline,receiver,notifier}.py |
| 7 | Telephony: call placement, call-state coordination, audio | managers/CallManager.kt, telephony/CallStateCoordinator.kt | paynet/telephony/{call_manager,coordinator}.py |
| 8 | Home dashboard screen | MainActivity.kt, MainScreenContent.kt, ui/home/{HomeDashboard,LegacyHomeDashboard,ModernHistoryPanel,HomeAppearance,HomeAppearancePreview}.kt, viewmodel/{MainViewModel,TransactionViewModel}.kt | paynet/ui/home.py, paynet/viewmodels.py |
| 9 | Transaction history + detail dialog | ui/activities/{TransactionHistoryActivity,TransactionPresentation}.kt, ui/components/TransactionDetailDialog.kt | paynet/ui/history.py |
| 10 | Pay-contact flow + contact picker | PayContactContent.kt, ui/dialogs/ContactPickerDialog.kt | paynet/ui/pay_contact.py |
| 11 | QR scanner | features/qr_scanner/** | paynet/qr/{scanner,parser,analyzer}.py |
| 12 | Setup + onboarding + appearance setup | SetupActivity.kt, SetupAdvanceState.kt, helpers/{SetupHelper,OnboardingFlow,MainActivityHelper}.kt, ui/dialogs/OnboardingDialog(+Copy).kt, OnboardingPage.kt, AppearanceSetupActivity.kt | paynet/ui/{setup,onboarding,appearance}.py |
| 13 | Settings screens | ui/activities/Settings*.kt | paynet/ui/settings.py |
| 14 | Payment result screen + progress dialogs + notifications | ui/activities/PaymentResultActivity.kt, ui/dialogs/{UssdProgressDialog,Upi123ProgressDialog}.kt, managers/TransactionDialogManager.kt, ui/components/{PaymentPromptLayout,PaymentAnswerButton,SmsPermissionNotice}.kt | paynet/ui/result.py, paynet/ui/prompts.py |
| 15 | Call overlay service | services/{CallOverlayService,CallOverlayView,CallOverlayMessageMotion}.kt, utils/OverlayLogger.kt | paynet/overlay/service.py |
| 16 | Diagnostics: test-configuration screen, permissions, install metrics | TestConfigurationActivity.kt, helpers/TestConfigurationHelper.kt, managers/PermissionManager.kt, metrics/{InstallReporter,InstallCountActivity}.kt, utils/ContextExt.kt, helpers/MainActivityHelper.kt | paynet/ui/diagnostics.py, paynet/permissions.py, paynet/metrics.py |
| 17 | Android packaging: buildozer, manifest parity (permissions, SMS receiver, overlay service), CI | AndroidManifest.xml, build.gradle.kts, .github/workflows/build.yml | kivy/buildozer.spec, CI job |

## Decisions

- **Plain Kivy, no KivyMD.** The Compose UI is a custom dark violet theme,
  not stock Material; Kivy widgets + the ported theme tokens give exact
  control with fewer dependencies.
- **Kivy app lives in `kivy/`** (package `paynet`, entry `kivy/main.py`,
  tests `kivy/tests`). The Kotlin app stays in place and buildable until
  the final phase.
- **sqlite3 (stdlib) replaces Room.** SQLCipher/Keystore at-rest encryption
  is a parity risk on the Python side — see *Parity risks*.
- **Android APIs via pyjnius** (dialer, telephony callbacks, SMS broadcast,
  contacts, camera, overlay window). CameraX + ZXing can stay as Gradle
  dependencies through buildozer; ZXing decode stays the same library.
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
| 6 | SMS ingestion pipeline + dedup + operation window | ⬜ Pending | | |
| 7 | Telephony: call placement, call-state coordination, audio | ◐ Partial | pytest (8 coordinator tests, 1:1) | CallStateCoordinator core ported with pluggable TelephonyAdapter; pyjnius adapter + CallManager pending |
| 8–17 | Remaining features | ⬜ Pending | | |

Test command: `cd kivy && python -m pytest tests -q`
Run command: `cd kivy && python main.py`
