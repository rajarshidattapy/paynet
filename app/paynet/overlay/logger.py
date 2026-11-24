# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/utils/OverlayLogger.kt

"""Structured overlay logging with consistent formatting. The sink is
injected (Logcat on Android); tests capture the formatted lines."""

from datetime import datetime

DATE_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


def _timestamp(now=None):
    moment = now or datetime.now()
    return moment.strftime(DATE_FORMAT)[:-3]


class OverlayLogger:
    def __init__(self, sink=print, clock=datetime.now):
        self._sink = sink
        self._clock = clock

    def _ts(self):
        return _timestamp(self._clock())

    def log_service_event(self, event, data=None):
        data = data or {}
        suffix = f" | Data: {data}" if data else ""
        self._sink(f"[{self._ts()}] SERVICE_EVENT: {event}{suffix}")

    def log_call_detection(self, phone_number, state, additional_info=""):
        phone_info = f" | Phone: {phone_number}" if phone_number is not None else " | Phone: null"
        extra = f" | {additional_info}" if additional_info else ""
        self._sink(f"[{self._ts()}] CALL_DETECTION: {state}{phone_info}{extra}")

    def log_overlay_state(self, action, success, error=None, details=None):
        details = details or {}
        status = "SUCCESS" if success else "FAILED"
        error_info = f" | Error: {error}" if error is not None else ""
        details_info = f" | Details: {details}" if details else ""
        self._sink(f"[{self._ts()}] OVERLAY_{action}: {status}{error_info}{details_info}")

    def log_permission_event(self, permission, granted, context=""):
        status = "GRANTED" if granted else "DENIED"
        context_info = f" | Context: {context}" if context else ""
        self._sink(f"[{self._ts()}] PERMISSION: {permission} = {status}{context_info}")

    def log_error(self, operation, error, context=None):
        context = context or {}
        context_info = f" | Context: {context}" if context else ""
        self._sink(f"[{self._ts()}] ERROR in {operation}{context_info}: {error}")

    def log_warning(self, operation, message, context=None):
        context = context or {}
        context_info = f" | Context: {context}" if context else ""
        self._sink(f"[{self._ts()}] WARNING in {operation}: {message}{context_info}")
