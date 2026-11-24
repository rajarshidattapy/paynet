# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/receivers/SimpleSMSReceiver.kt

"""The SMS_RECEIVED entry point.

DEVIATION: the Android BroadcastReceiver binding — PDU extraction via
Telephony.Sms.Intents.getMessagesFromIntent, goAsync() process lifetime —
is pyjnius/manifest work tracked under packaging (feature 17) and UNVERIFIED
from desktop. What ports 1:1 is the guard logic in handle_sms: ignore
blank bodies, require an active operation window, claim the message so a
redelivered broadcast can't process it twice, then hand off to the shared
ingestion pipeline. The Kotlin runs the pipeline on Dispatchers.IO with an
8s bound under goAsync(); this synchronous port relies on the caller's
threading (documented in MIGRATION.md).
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from .detector import TransactionDetector

log = logging.getLogger("SimpleSMSReceiver")


class SimpleSMSReceiver:
    def __init__(
        self,
        detector: TransactionDetector,
        ingest: Callable[[TransactionDetector, str, str], object],
    ) -> None:
        self._detector = detector
        self._ingest = ingest

    def handle_sms(self, sender: Optional[str], body: str) -> bool:
        """One delivered SMS (already assembled from its PDUs by the
        platform binding). Returns True when the message went to the
        ingestion pipeline."""
        if not sender:
            return False
        if not body or not body.strip():
            return False

        log.debug("SMS received")

        if not self._detector.should_process_sms():
            log.debug("No active payment operation, ignoring SMS")
            return False

        # Claim this exact message so a redelivered SMS_RECEIVED broadcast
        # can't process the same SMS a second time.
        if not self._detector.try_claim_sms(body):
            log.debug("SMS already claimed")
            return False

        try:
            self._ingest(self._detector, sender, body)
        except Exception:
            log.exception("Failed to process SMS")
        return True
