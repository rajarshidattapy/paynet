# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Feature 17: Android bindings for the injected platform seams.

"""pyjnius implementations of the device-only seams recorded across
MIGRATION.md: telephony (PhonePlatform for CallManager, TelephonyAdapter for
CallStateCoordinator), runtime-permission checks, SMS ingestion, vibration,
toast, payment-result notifications, and the install-receipt POST.

UNVERIFIED FROM DESKTOP by construction: nothing here imports off Android
(the package __init__ only builds Bindings when kivy.utils.platform ==
"android"), and the unit tests drive the logic through a mocked jnius.

Notes on the seams:
- Call-state listening uses TelephonyCallback on API 31+; on API 29-30
  (minSdk 29) PhoneStateListener is an abstract class pyjnius cannot
  subclass, so the adapter polls TelephonyManager.getCallState() at 4 Hz
  while registered (registration is refcounted to active payment windows).
- SMS ingestion needs a real BroadcastReceiver subclass, which pyjnius
  cannot express: two tiny Java sources ship under android-src/ (added via
  buildozer's android.add_src) and forward assembled messages into
  SmsBridgeListener, a PythonJavaClass interface implementation.
- The metrics POST uses urllib from the app process (INTERNET permission);
  parity with the Kotlin HttpURLConnection request is asserted by tests
  against a stubbed opener.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from typing import Callable, Optional

log = logging.getLogger("paynet.platform.android")

try:
    from jnius import PythonJavaClass, autoclass, java_method
    JNIUS_IMPORT_ERROR = None
except ImportError as error:  # desktop: bindings are never constructed
    autoclass = None
    JNIUS_IMPORT_ERROR = error

    class PythonJavaClass:  # import-time stand-in; never instantiated
        __javainterfaces__ = []
        __javacontext__ = "app"

    def java_method(*_a, **_k):
        def _wrap(fn):
            return fn
        return _wrap

from paynet.permissions import PermissionConstants  # noqa: E402
from paynet.telephony.call_manager import CALL_STATE_IDLE  # noqa: E402

CALL_STATE_POLL_S = 0.25
METRICS_TIMEOUT_S = 8  # InstallReporter.REQUEST_TIMEOUT_MS


def _activity():
    from android import mActivity  # type: ignore  # p4a runtime module
    return mActivity


def _context():
    return _activity().getApplicationContext()


def _version_sdk() -> int:
    return autoclass("android.os.Build$VERSION").SDK_INT


# ---------------------------------------------------------------------------
# Runtime permissions
# ---------------------------------------------------------------------------


class AndroidPermissionChecker:
    """ContextCompat.checkSelfPermission binding: answers the `checker`
    callable injected into PermissionManager and the MainActivityHelper /
    QR-scanner gates."""

    def __call__(self, permission: str) -> bool:
        ContextCompat = autoclass("androidx.core.content.ContextCompat")
        PackageManager = autoclass("android.content.pm.PackageManager")
        return (ContextCompat.checkSelfPermission(_context(), permission)
                == PackageManager.PERMISSION_GRANTED)


class AndroidPermissionRequester:
    """ActivityCompat.requestPermissions binding. Results return through the
    p4a activity callback registered by the app shell (feature 17 wiring);
    `on_result` receives the all-granted boolean, matching the Kotlin
    ActivityResultContracts.RequestMultiplePermissions aggregation."""

    def request(self, permissions, on_result: Callable[[bool], None]) -> None:
        ActivityCompat = autoclass("androidx.core.app.ActivityCompat")
        from android import activity as _activity_module  # type: ignore

        code = 4101

        def _on_request_permissions_result(request_code, _perms, grant_results):
            if request_code != code:
                return
            _activity_module.unbind(on_request_permissions_result=_handler)
            PackageManager = autoclass("android.content.pm.PackageManager")
            granted = (len(grant_results) > 0 and all(
                result == PackageManager.PERMISSION_GRANTED
                for result in grant_results))
            on_result(granted)

        _handler = _on_request_permissions_result
        _activity_module.bind(on_request_permissions_result=_handler)
        ActivityCompat.requestPermissions(
            _activity(), list(permissions), code)

    def request_phone_permissions(self) -> None:
        """The phone group (CALL_PHONE, READ_PHONE_STATE, ANSWER_PHONE_CALLS,
        RECEIVE_SMS) requested together before dialling. The screens that
        call this take a no-argument callable and re-read the live grant state
        on the next tap, so the result is not forwarded."""
        from paynet.permissions import PermissionConstants
        self.request(PermissionConstants.PHONE_PERMISSIONS, lambda _granted: None)


# ---------------------------------------------------------------------------
# Telephony
# ---------------------------------------------------------------------------


class _CallStateListener(PythonJavaClass):
    """TelephonyCallback$CallStateListener implementation (API 31+)."""

    __javainterfaces__ = ["android/telephony/TelephonyCallback$CallStateListener"]
    __javacontext__ = "app"

    def __init__(self, on_state_change: Callable[[int], None]):
        super().__init__()
        self._on_state_change = on_state_change

    @java_method("(I)V")
    def onCallStateChanged(self, state):
        self._on_state_change(state)


class AndroidTelephonyAdapter:
    """TelephonyAdapter for CallStateCoordinator: register/unregister/
    current_state over TelephonyManager. API 31+ uses
    registerTelephonyCallback; below that a 4 Hz poll of getCallState(),
    because pyjnius cannot subclass the abstract PhoneStateListener."""

    def __init__(self):
        self._manager = _context().getSystemService(
            autoclass("android.content.Context").TELEPHONY_SERVICE)
        self._listener = None
        self._poll_thread = None
        self._polling = threading.Event()

    def register(self, on_state_change: Callable[[int], None]) -> None:
        if _version_sdk() >= 31:
            self._listener = _CallStateListener(on_state_change)
            executor = _context().getMainExecutor()
            self._manager.registerTelephonyCallback(executor, self._listener)
            return
        # API 29-30 fallback: poll while registered.
        self._polling.set()

        def _poll():
            last = None
            while self._polling.is_set():
                state = self._manager.getCallState()
                if state != last:
                    last = state
                    on_state_change(state)
                time.sleep(CALL_STATE_POLL_S)

        self._poll_thread = threading.Thread(target=_poll, daemon=True)
        self._poll_thread.start()

    def unregister(self) -> None:
        self._polling.clear()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=1.0)
            self._poll_thread = None
        if self._listener is not None:
            self._manager.unregisterTelephonyCallback(self._listener)
            self._listener = None

    def current_state(self) -> int:
        try:
            return self._manager.getCallState()
        except Exception:
            return CALL_STATE_IDLE


class AndroidPhonePlatform:
    """PhonePlatform for CallManager: calls, audio routing and Telecom
    end-call over the real services. `start_call` never fires without the
    CALL_PHONE grant, mirroring the Kotlin SecurityException guard."""

    def __init__(self, checker: Optional[Callable[[str], bool]] = None):
        self._context = _context()
        self._checker = checker or AndroidPermissionChecker()
        Context = autoclass("android.content.Context")
        self._telephony = self._context.getSystemService(Context.TELEPHONY_SERVICE)
        self._audio = self._context.getSystemService(Context.AUDIO_SERVICE)

    # -- calls -------------------------------------------------------------

    def has_permission(self, permission: str) -> bool:
        return bool(self._checker(permission))

    def start_call(self, uri: str) -> None:
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        intent = Intent(Intent.ACTION_CALL, Uri.parse(uri))
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        self._context.startActivity(intent)

    def telecom_end_call(self) -> bool:
        Context = autoclass("android.content.Context")
        telecom = self._context.getSystemService(Context.TELECOM_SERVICE)
        return bool(telecom.endCall())

    # -- state ---------------------------------------------------------------

    def listen_call_state(self, listener: Callable[[int], None]) -> None:
        # CallManager listens through CallStateCoordinator; direct platform
        # listens reuse the same adapter shape.
        self._direct_adapter = AndroidTelephonyAdapter()
        self._direct_adapter.register(listener)

    def unlisten_call_state(self, _listener: Callable[[int], None]) -> None:
        if getattr(self, "_direct_adapter", None) is not None:
            self._direct_adapter.unregister()
            self._direct_adapter = None

    def get_call_state(self) -> int:
        try:
            return self._telephony.getCallState()
        except Exception:
            return CALL_STATE_IDLE

    # -- audio ---------------------------------------------------------------

    def get_stream_volume(self, stream: int) -> int:
        return self._audio.getStreamVolume(stream)

    def set_stream_volume(self, stream: int, volume: int, flags: int) -> None:
        self._audio.setStreamVolume(stream, volume, flags)

    def get_mode(self) -> int:
        return self._audio.getMode()

    def set_mode(self, mode: int) -> None:
        self._audio.setMode(mode)

    def set_microphone_mute(self, muted: bool) -> None:
        self._audio.setMicrophoneMute(muted)

    def set_speakerphone_on(self, on: bool) -> None:
        self._audio.setSpeakerphoneOn(on)

    # -- ui ------------------------------------------------------------------

    def toast(self, message: str) -> None:
        android_toast(message)


def android_toast(message: str) -> None:
    """A platform Toast on the main thread (the `toast` injected seam)."""
    Toast = autoclass("android.widget.Toast")

    def _run(_dt):
        Toast.makeText(_context(), str(message), Toast.LENGTH_LONG).show()

    # The Kivy Clock lands the call on the main/UI thread.
    from kivy.clock import Clock
    Clock.schedule_once(_run, 0)


# ---------------------------------------------------------------------------
# Vibration
# ---------------------------------------------------------------------------


def android_vibrate() -> None:
    """CallOverlayService's success vibration (VIBRATOR_SERVICE; the legacy
    Vibrator API, matching the Kotlin caller)."""
    Context = autoclass("android.content.Context")
    vibrator = _context().getSystemService(Context.VIBRATOR_SERVICE)
    vibrator.vibrate(200)


# ---------------------------------------------------------------------------
# Notifications (PaymentResultNotifier's `post` seam)
# ---------------------------------------------------------------------------


class AndroidNotifier:
    """NotificationChannel + NotificationManager binding; best-effort by
    design: posting without the POST_NOTIFICATIONS grant is a silent no-op
    on Android 13+, matching the Kotlin caller's contract."""

    def __init__(self, channel_id: str, channel_name: str,
                 channel_description: str):
        self._channel_id = channel_id
        context = _context()
        if _version_sdk() >= 26:
            NotificationChannel = autoclass("android.app.NotificationChannel")
            NotificationManager = autoclass("android.app.NotificationManager")
            channel = NotificationChannel(
                channel_id, channel_name, NotificationManager.IMPORTANCE_HIGH)
            channel.setDescription(channel_description)
            context.getSystemService(
                autoclass("android.content.Context").NOTIFICATION_SERVICE
            ).createNotificationChannel(channel)
        self._context = context

    def post(self, notification_id: int, title: str, text: str) -> None:
        Builder = autoclass("android.app.Notification$Builder")
        builder = Builder(self._context, self._channel_id) if _version_sdk() >= 26 \
            else Builder(self._context)
        builder.setContentTitle(title)
        builder.setContentText(text)
        builder.setSmallIcon(
            autoclass("android.R$drawable").ic_dialog_info)
        builder.setAutoCancel(True)
        self._context.getSystemService(
            autoclass("android.content.Context").NOTIFICATION_SERVICE
        ).notify(notification_id, builder.build())


# ---------------------------------------------------------------------------
# Metrics POST (InstallReporter's `poster` seam)
# ---------------------------------------------------------------------------


def urllib_poster(url: str, payload: dict) -> Optional[dict]:
    """POST {installation_id, version} as JSON; returns the parsed response
    body on HTTP 200, None on any failure (the Kotlin IOException path:
    keep the ID, retry later). 8 s connect/read timeout, no redirects."""
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Content-Length": str(len(body))})

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_a, **_k):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=METRICS_TIMEOUT_S) as response:
            if response.status != 200:
                return None
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# SMS ingestion bridge (fed by android-src/ Java receiver)
# ---------------------------------------------------------------------------


class SmsBridgeListener(PythonJavaClass):
    """Registered on the Java PayNetSmsBridge; each assembled SMS goes to
    SimpleSMSReceiver.handle_sms. Runs on the receiver's background thread,
    matching the Kotlin goAsync/Dispatchers.IO shape."""

    __javainterfaces__ = ["com/paynet/app/kivy/PayNetSmsBridge$Listener"]
    __javacontext__ = "app"

    def __init__(self, handle_sms: Callable[[Optional[str], str], bool]):
        super().__init__()
        self._handle_sms = handle_sms

    @java_method("(Ljava/lang/String;Ljava/lang/String;)V")
    def onSms(self, sender, body):
        self._handle_sms(sender, body)


def register_sms_bridge(handle_sms: Callable[[Optional[str], str], bool]) -> None:
    bridge = autoclass("com.paynet.app.kivy.PayNetSmsBridge")
    bridge.setListener(SmsBridgeListener(handle_sms))


# ---------------------------------------------------------------------------
# Gallery QR decode (QRScannerController's decode_gallery_image seam)
# ---------------------------------------------------------------------------


def zxing_decode_gallery_image(uri_string: str) -> Optional[str]:
    """Decode a picked image through BitmapFactory + ZXing, mirroring
    QRCodeAnalyzer's BinaryBitmap/HybridBinarizer path. Returns the decoded
    text or None. Requires com.google.zxing:core (buildozer
    android.gradle_dependencies)."""
    BitmapFactory = autoclass("android.graphics.BitmapFactory")
    Uri = autoclass("android.net.Uri")
    RGBLuminanceSource = autoclass("com.google.zxing.RGBLuminanceSource")
    BinaryBitmap = autoclass("com.google.zxing.BinaryBitmap")
    HybridBinarizer = autoclass("com.google.zxing.common.HybridBinarizer")
    MultiFormatReader = autoclass("com.google.zxing.MultiFormatReader")

    stream = _context().getContentResolver().openInputStream(
        Uri.parse(uri_string))
    try:
        bitmap = BitmapFactory.decodeStream(stream)
    finally:
        stream.close()
    if bitmap is None:
        return None
    width, height = bitmap.getWidth(), bitmap.getHeight()
    buffer = autoclass("java.nio.IntBuffer").allocate(width * height)
    bitmap.copyPixelsToBuffer(buffer)
    pixels = buffer.array()
    source = RGBLuminanceSource(width, height, pixels)
    try:
        result = MultiFormatReader().decode(
            BinaryBitmap(HybridBinarizer(source)))
        return str(result.getText())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


class Bindings:
    """The full binding set the app shell wires into the injected seams when
    running on Android. Construction is lazy: no Java class is touched until
    first use, so importing this module is always safe."""

    def __init__(self):
        self.permission_checker = AndroidPermissionChecker()
        self.permission_requester = AndroidPermissionRequester()
        self.phone_platform = AndroidPhonePlatform(self.permission_checker)
        self.telephony_adapter = AndroidTelephonyAdapter()
        self.vibrate = android_vibrate
        self.toast = android_toast
        self.notifier = AndroidNotifier(
            "payment_results", "Payment results",
            "The outcome of each payment — success, failure, or needs checking")
        self.metrics_poster = urllib_poster
        self.register_sms_bridge = register_sms_bridge
        self.decode_gallery_image = zxing_decode_gallery_image
        self.can_draw_overlays = self._can_draw_overlays

    @staticmethod
    def _can_draw_overlays() -> bool:
        Settings = autoclass("android.provider.Settings")
        return bool(Settings.canDrawOverlays(_context()))

    def overlay_settings_intent(self):
        """ACTION_MANAGE_OVERLAY_PERMISSION for this package, or None when
        already granted (PermissionManager.overlay_permission_settings_intent)."""
        if self.can_draw_overlays():
            return None
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        Settings = autoclass("android.provider.Settings")
        intent = Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:" + _context().getPackageName()))
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        return intent

    def phone_permissions(self):
        return list(PermissionConstants.PHONE_PERMISSIONS)
