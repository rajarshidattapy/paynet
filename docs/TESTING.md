# Testing PayNet

PayNet's core claim — a payment outcome is only ever recorded from a
confirming bank SMS, never from call duration — can't be end-to-end tested
the way a normal app is: there's no test double for an Indian bank, a UPI
switch, or a telco's IVR menu. This is PayNet's honest answer to "how do
you know it works" without one.

Verification happens in layers, each covering what the layer below it
cannot. One caveat applies to all of them today: the Python port has not yet
been packaged for Android (feature 17 in [MIGRATION.md](../MIGRATION.md)).
Everything that only exists on a device — dialling, call-state callbacks, SMS
broadcast reception, notifications, camera decode, the overlay window — is an
injected callable that the tests replace with a fake. Those bindings are
**unverified** until the device layer below exists.

## Layer 1 — Hermetic unit tests (CI, every push)

Pure logic, no device, no real call, no real SMS. The whole suite runs in
seconds:

```bash
cd kivy
python -m pytest tests -q
```

CI runs the same command on every push and pull request (under `xvfb-run`,
because modules that import Kivy widgets need a display even when no window
is opened). The money-path suites:

- **[`test_sms_parser.py`](../kivy/tests/test_sms_parser.py)** — the
  bank-SMS matching logic ([`paynet/sms/parser.py`](../kivy/paynet/sms/parser.py)),
  exercised end-to-end via `parse()` across a corpus covering every
  supported bank, success/failure/credit/non-UPI-debit-alert shapes, and
  amount-format edge cases.
  [`test_sms_regex.py`](../kivy/tests/test_sms_regex.py) covers the
  individual regex-backed building blocks (bank detection, dedup key
  convergence, amount tolerance) the same way.
- **[`test_payment_session.py`](../kivy/tests/test_payment_session.py)** —
  the payment lifecycle state machine
  ([`paynet/payment/session.py`](../kivy/paynet/payment/session.py)), driven
  with a fake call-state source, a fake store, a fake clock and a manual
  watchdog. Covers the PENDING-before-dial invariant, every terminal
  transition (Success/Failed/NeedsReview/Cancelled/Timeout — where a Timeout
  discards the unconfirmed row and a later SMS cannot resurrect a cancelled
  one), that `on_user_cancelled`/`on_call_never_started` reach a correct,
  idempotent terminal state even when called defensively more than once
  (the scenario `CallOverlayService`'s cleanup paths rely on), and two
  real-thread race tests
  (`test_truly_concurrent_confirmations_exactly_one_claims_the_session`,
  `test_concurrent_cancel_and_confirmation_never_disagree`).
- **[`test_sms_pipeline.py`](../kivy/tests/test_sms_pipeline.py)**,
  **[`test_sms_receiver_notifier.py`](../kivy/tests/test_sms_receiver_notifier.py)**
  and **[`test_payment_window.py`](../kivy/tests/test_payment_window.py)** —
  orphaned-row adoption, unrelated-credit handling, operation-window expiry
  and dedup (including a concurrent double-delivery), the receiver's guards,
  and closing the SMS window on every cancel route.
- **[`test_database.py`](../kivy/tests/test_database.py)** — the sqlite
  lifecycle guards: a confirmation never rewrites a cancelled row, and only
  expired PENDING rows are discarded.
- **[`test_call_string.py`](../kivy/tests/test_call_string.py)** — the DTMF
  dial-string builder, golden strings plus injection-neutralization cases.
- **[`test_qr_scanner.py`](../kivy/tests/test_qr_scanner.py)** — UPI QR URI
  parsing, the analyzer's normal-then-inverted decode order and duplicate
  latch, and the scanner flow (session begin, dial-once guard, dial failure
  cancelling the session). The ZXing decode itself is an injected callable
  here, so — unlike the Kotlin suite this was ported from — there is no
  corpus that encodes real QR images and decodes them back.

Most UI rules (history grouping, result-screen styling, setup and settings
flows, overlay pacing) also run here, because the logic lives in plain
Python helpers rather than inside widgets.

### Visual checks — headless screen renders (manual)

`kivy/render_*.py` are dev-only scripts that build one screen in a
fixed-size window, put it in a named state, and save a screenshot under
`/downloads/`. They are how the port's screens were compared against the
Kotlin originals. They are not run in CI. For example:

```bash
cd kivy
python render_result.py failed
python render_home.py empty legacy
```

The first argument is the state name; each script lists the states it
accepts.

## Layer 2 — Device tests (none at present)

There are currently **no tests that run on a device or emulator**, and no
emulator job in CI. The Kotlin app's instrumented suite (including its
synthetic SMS integration tests) was not ported, because there is no Android
build of the Python app to run it against yet.

This layer comes back with Android packaging (feature 17). The persistence
side has a second debt: the sqlite schema has no version number and no
migrations (see [ARCHITECTURE.md](ARCHITECTURE.md#persistence)), so the next
schema change must land with its migration and a test for it.

## Layer 3 — Replaying a bank SMS through the live pipeline (any desktop, on demand)

Layer 1 proves each part in isolation. It does not prove the *wiring* — that
an SMS reaching the receiver actually flows through session confirmation,
persistence, and the result. The Kotlin app closed that gap with a
debug-only broadcast receiver driven over `adb`. The Python port has no
receiver to drive yet, but the same goal is reachable more directly: the
ingestion pipeline ([`paynet/sms/pipeline.py`](../kivy/paynet/sms/pipeline.py))
is a plain function, so you can feed it a bank SMS with the real detector,
session manager and sqlite repository wired together, no SIM, bank or call
involved.

Save this as a script and run it from `kivy/` with `python - < script.py`
(so `paynet` is importable):

```python
import tempfile

from paynet.db.database import Database
from paynet.db.settings import PrefsStore
from paynet.payment.session import PaymentSessionManager
from paynet.payment.window import PaymentWindowObserver
from paynet.repository import TransactionRepository
from paynet.sms import pipeline
from paynet.sms.detector import TransactionDetector
from paynet.telephony.coordinator import CallStateCoordinator

data_dir = tempfile.mkdtemp(prefix="paynet-replay-")
repo = TransactionRepository(Database(f"{data_dir}/paynet.db"))
detector = TransactionDetector(PrefsStore(data_dir, "TransactionDetector"))
session = PaymentSessionManager(store=repo,
                                coordinator=CallStateCoordinator(telephony=None))
PaymentWindowObserver(session, on_disarm=detector.stop_operation).start()

# 1. Start a payment and open its SMS window (what tapping "Pay" does)
txn_id = session.begin("9876543210", "500")
detector.start_operation("UPI_123", expected_amount="500",
                         phone_number="9876543210", session_txn_id=txn_id)

# 2. Deliver a bank confirmation SMS — any redacted sample from the
#    tests/test_sms_parser.py corpus works
pipeline.ingest(
    detector, "VK-HDFCBK",
    "Rs.500.00 sent to KIRANA STORE from HDFC Bank A/c **1234 via UPI ref 512233440091",
    session_manager=session, repository=repo,
    open_result=lambda result: print("result screen:", result["status"], result["amount"]))

print(session.payment_state)
print(repo.get_transaction_by_id(txn_id).status)
```

It should print a `SUCCESS` result for ₹500, a `Success` session state, and
a `SUCCESS` row — the same outcome a real bank SMS produces.

What this does **not** cover is the part that is still missing: the Android
receiver binding that turns an `SMS_RECEIVED` broadcast into the
`handle_sms(sender, body)` call, and the notification and result-screen
launch behind `notifier`/`open_result`. Those can only be verified on a
device once packaging exists.

### Money-path scenarios worth re-running

Each of these is pinned by a Layer 1 test, and each can also be replayed
with the script above by changing the SMS (or the steps):

- **Dual-verb template.** Inject `AD-ICICIB` / *"ICICI Bank Acct XX556
  debited for Rs 500.00 on 29-Jul-26; KIRANA STORE credited. UPI:512233440091"*
  into a ₹500 window. It must confirm. Read as an incoming credit (the bug
  this guards) it would be dropped as unrelated and the payment would never
  appear. (`test_dual_verb_debit_template_confirms_the_payment_it_belongs_to`)
- **Mismatched amount.** The same template for ₹900 against a ₹500 window
  must produce nothing and leave the window open, so a following ₹500
  confirmation still lands.
  (`test_dual_verb_debit_for_a_different_amount_is_still_dropped`)
- **Unrelated incoming credit.** A genuine `credited`-only body during an
  open window must be ignored without closing the window.
  (`test_unclaimed_incoming_credit_in_the_window_is_ignored`,
  `test_a_credit_match_does_not_consume_the_window`)
- **Cancel really cancels.** Call `session.on_user_cancelled()` (what the
  overlay's *Cancel payment* does), then inject a matching debit. Nothing
  should surface, the row must stay CANCELLED, and `TransactionDetector.json`
  in the data directory should be empty — the window cleared.
  (`test_a_confirming_sms_cannot_resurrect_a_cancelled_row`,
  `test_observer_disarms_on_user_cancellation`)
- **No SMS, no record.** Open a window, inject nothing, and let the deadline
  pass (construct the session with a small `verification_deadline_ms` to
  avoid waiting ten minutes): the state becomes `Timeout` and no row
  remains. (`test_no_sms_before_deadline_discards_the_row_and_emits_timeout`)

In the running desktop app, `PaymentWindowObserver` is not wired yet (see
[ARCHITECTURE.md](ARCHITECTURE.md#composition-root)); the script wires it by
hand.

## Layer 4 — Physical-device release gate (human, per release)

The layers above are hermetic by design and deliberately cannot prove the
parts that actually touch a telco or a bank: whether `*99#` still dials
cleanly on a given operator, whether 123Pay's IVR flow still matches the
expected DTMF timing, and whether a bank's SMS template still matches what
the corpus expects. That requires a real device with a real SIM.

For the Python port this gate does not exist yet: there is no Android build
to put on a device. When packaging lands, the device-only items listed under
*Not verified from desktop* in [MIGRATION.md](../MIGRATION.md) are the
minimum it must cover before any release.

## What this doesn't cover

Layers 1 and 3 are hermetic and can lag reality if a bank changes its SMS
template — that's exactly what Layer 4 exists to catch before a release
ships, and exactly why growing the Layer 1 corpus (see "Adding a bank SMS
template" in [CONTRIBUTING.md](CONTRIBUTING.md)) is one of the most valuable
contributions this project can take.
