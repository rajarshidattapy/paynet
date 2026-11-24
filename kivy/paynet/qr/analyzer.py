# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay

"""QR analyzer — 1:1 port of features/qr_scanner/domain/QRCodeAnalyzer.kt.

The ZXing-backed decode is device-only (CameraX ImageProxy -> Y-plane
luminance -> ZXing MultiFormatReader); here the decode of one luminance
source is injected as ``decode_source`` and the inverted-copy producer as
``invert_source`` (ZXing LuminanceSource.invert()). Everything around the
decode — the normal-then-inverted pipeline, the 2-second duplicate
threshold, the processing latch, the broad never-crash catch — is ported
exactly. The pyjnius binding to ZXing lands with feature 17.
"""

import time

# 2 seconds.
DUPLICATE_DETECTION_THRESHOLD_MS = 2000

# Longest edge a gallery image is downsampled to before decoding.
GALLERY_MAX_EDGE_PX = 2048


class QRCodeAnalyzer:
    def __init__(self, on_qr_code_detected, decode_source,
                 invert_source=None, clock=None):
        """on_qr_code_detected: called with the decoded text.
        decode_source(source) -> Optional[str]: one ZXing decode attempt.
        invert_source(source) -> source: the inverted luminance copy."""
        self._on_detected = on_qr_code_detected
        self._decode_source = decode_source
        self._invert_source = invert_source or (lambda source: None)
        self._clock = clock or (lambda: int(time.monotonic() * 1000))
        self._last_detected_code = None
        self._last_detection_time = 0
        self.is_processing = False

    def analyze(self, frame):
        """One camera frame in, at most one detection callback out. The
        frame is always closed (ImageProxy.close()), even on the early
        returns."""
        try:
            if self.is_processing:
                return None

            qr_code = self._decode(frame)
            if qr_code is None:
                return None
            current_time = self._clock()
            is_duplicate = (
                self._last_detected_code == qr_code
                and current_time - self._last_detection_time
                < DUPLICATE_DETECTION_THRESHOLD_MS
            )
            if is_duplicate:
                return None

            self.is_processing = True
            self._last_detected_code = qr_code
            self._last_detection_time = current_time
            self._on_detected(qr_code)
            return qr_code
        finally:
            close = getattr(frame, "close", None)
            if callable(close):
                close()

    def _decode(self, source):
        """Try the frame as captured, then an inverted copy — handles
        dark-QR-on-light-background and the light-on-dark inverse."""
        result = self._decode_source_safe(source)
        if result is not None:
            return result
        inverted = self._invert_source(source)
        if inverted is None:
            return None
        return self._decode_source_safe(inverted)

    def _decode_source_safe(self, source):
        # A camera frame is untrusted input arriving continuously; this
        # screen must never crash on a malformed one, so the fallback catch
        # is broad. No valid QR in the frame is the overwhelmingly common
        # outcome while the camera is idle, not an error.
        try:
            return self._decode_source(source)
        except Exception:
            return None

    def reset_processing(self):
        """Reset the processing flag to allow new QR code detection."""
        self.is_processing = False


def decode_bitmap(bitmap, decode_source, invert_source=None):
    """One-shot decode of a static image (e.g. a QR code picked from the
    gallery) — same pipeline as the live camera analyzer, just fed an RGB
    bitmap instead of a YUV camera frame."""
    invert = invert_source or (lambda source: None)

    def safe(source):
        try:
            return decode_source(source)
        except Exception:
            return None

    result = safe(bitmap)
    if result is not None:
        return result
    inverted = invert(bitmap)
    if inverted is None:
        return None
    return safe(inverted)
