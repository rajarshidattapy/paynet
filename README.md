<p align="center">
  <img src="docs/readme/paynet-wordmark.png" width="240" alt="PayNet">
</p>

<h3 align="center">UPI payments, even offline.</h3>

<p align="center">
  An Android app for paying over <code>*99#</code> USSD and UPI 123PAY when mobile data is gone but the cellular network is not.
</p>

<p align="center">
  <a href="https://github.com/rajarshidattapy/paynet/actions/workflows/build.yml"><img src="https://github.com/rajarshidattapy/paynet/actions/workflows/build.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-6A4FF0" alt="Apache 2.0"></a>
  <img src="https://img.shields.io/badge/Android-10%2B-6A4FF0" alt="Android 10+">
  <img src="https://img.shields.io/badge/Python-Kivy-6A4FF0" alt="Python + Kivy">
</p>

---

Mobile data drops. UPI apps stop at the login screen. The phone can still place a call, and India's offline payment rails still work — PayNet is the interface that gets you to them.

No account. No wallet. No data connection. Scan a QR code or pick a contact, and PayNet walks the payment through your bank's own USSD or voice flow while an on-screen guide keeps the steps in view.

<p align="center">
  <img src="docs/home.png" width="300" alt="PayNet home screen">
</p>

## What it does

- **Scan QR → `*99#` USSD.** Point the camera at any UPI QR code and follow the bank's payment menu in the dialler.
- **Pay Contact → UPI 123PAY.** Choose a contact or paste a number, enter the amount, and complete the call-based IVR flow with the on-screen guide alongside.
- **Two rails, one fallback.** `*99#` is unavailable on Jio; the phone-number route uses UPI 123PAY, including on Jio where supported. Availability still depends on your bank and operator, so setup checks both.
- **On-device history.** Bank confirmation messages matched during an active payment window supply the outcome. Records stay on your phone — nothing is uploaded.

Your bank handles the money. PayNet never holds funds and never sees your UPI PIN — that is entered only in the bank's dialler or IVR.

## Why it exists

A declined transaction and a payment that never starts are different problems. India already has payment services that work without mobile data — `*99#` over USSD and UPI 123PAY over a voice call — but finding the right menu, in the right order, mid-payment, is where people give up. PayNet owns that last mile: recipient selection, QR scanning, step guidance and outcome matching, while the bank's flow does the banking.

## Engineering notes

**The app does not own the whole flow.** USSD menus and voice calls run outside the app. The hand-off to the dialler is unavoidable, so PayNet provides an on-screen guide during calls. It does not use an accessibility service to read or control another app.

**A call ending is not a payment confirmation.** Neither rail gives a reliable success callback. Incoming bank messages are matched only during an active payment window, duplicate messages do not create duplicate results, and a missing confirmation never becomes an assumed outcome.

**History stays on the device.** Payment records live in a local SQLite database in the app's data directory. At-rest encryption (SQLCipher with an Android Keystore-protected key) is not yet carried over to the Python build — see [MIGRATION.md](MIGRATION.md#parity-risks).

**Your PIN stays with your bank.** Enter it in the bank's USSD or call flow. PayNet does not read or store it.

## Running it

You need Python 3.11 or later.

```sh
git clone https://github.com/rajarshidattapy/paynet.git
cd paynet/kivy
python -m pip install -r requirements.txt
python main.py               # launch the app in a desktop window
python -m pytest tests -q    # run the test suite
```

On desktop, everything that needs a phone (USSD dialling, the IVR call, SMS reception, camera, the overlay during a call) is replaced by a stand-in, so no real payment is ever triggered. Each `render_*.py` script in `kivy/` renders one screen headlessly so you can check it visually.

Android packaging (buildozer plus pyjnius bindings for SMS, telephony, camera and the overlay) is not done yet — see [MIGRATION.md](MIGRATION.md). Once it exists, using the app will need **Android 10 or later**, an **Indian SIM linked to a UPI-enabled bank account**, and cellular coverage with support for your chosen route.

## Reading the code

Python and Kivy, stdlib `sqlite3` for persistence. The app is the `paynet` package under `kivy/`. Start here:

| File | What to look for |
| :--- | :--- |
| [`payment/call_string.py`](kivy/paynet/payment/call_string.py) | Recipient and amount validation before constructing the call's DTMF string. |
| [`payment/session.py`](kivy/paynet/payment/session.py) | Payment lifecycle and state transitions (`PaymentSessionManager`). |
| [`telephony/call_manager.py`](kivy/paynet/telephony/call_manager.py) | Dialler interaction, call state and audio restoration, behind a fakeable `PhonePlatform`. |
| [`overlay/service.py`](kivy/paynet/overlay/service.py) | The on-screen guide during a call. |
| [`sms/pipeline.py`](kivy/paynet/sms/pipeline.py) | Matching bank SMS to the active payment window, with de-duplication. |

More detail lives in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/TESTING.md](docs/TESTING.md) and [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md).

## Security

PayNet touches payment flows, USSD dialling and SMS parsing. **Do not file public issues for vulnerabilities** — see [docs/SECURITY.md](docs/SECURITY.md) for the reporting address, supported versions and the data-handling threat model.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE). PayNet is an independent project, not affiliated with NPCI, any bank or any telecom operator.
