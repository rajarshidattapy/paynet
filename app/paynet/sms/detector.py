# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/helpers/TransactionDetector.kt

"""Stateful orchestration around SmsTransactionParser: the prefs-backed
operation window (only SMS arriving while a payment is in flight are
eligible) and dedup so one SMS is never processed twice.

All actual bank-SMS matching logic lives in paynet.sms.parser, which is pure.

DEVIATION: SharedPreferences becomes the JSON-backed PrefsStore, and the
Java String.hashCode claim key becomes the claim-key string itself (dedup
semantics identical: one stable key per normalised body). The Context
singleton becomes a plain instance wired by the app container.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Optional

from ..payment.session import DEFAULT_VERIFICATION_DEADLINE_MS
from . import parser as sms_parser
from .parser import SimpleTransaction

log = logging.getLogger("TransactionDetector")

KEY_ACTIVE = "is_active"
KEY_START_TIME = "start_time"
KEY_OPERATION_TYPE = "operation_type"
KEY_EXPECTED_AMOUNT = "expected_amount"
KEY_PHONE_NUMBER = "phone_number"
KEY_SESSION_TXN_ID = "session_txn_id"

# How long after a payment starts an incoming SMS is still eligible. Derived
# from the session verification deadline (plus a grace margin for a
# confirmation racing the deadline) — it must never be shorter, or a
# slow-but-genuine bank SMS would be dropped here and a payment that did go
# through would never be recorded.
OPERATION_WINDOW_MILLIS = DEFAULT_VERIFICATION_DEADLINE_MS + 30_000

SMS_CLAIM_WINDOW_MILLIS = 60 * 1000  # dedupe window across pipelines

_MAX_RECENT_CLAIMS = 64


class TransactionDetector:
    """One instance per app (wired by the container; the Kotlin used a
    Context-scoped singleton). `prefs` is a PrefsStore named
    "payment_operation"."""

    def __init__(self, prefs, clock=lambda: int(time.time() * 1000)) -> None:
        self._prefs = prefs
        self._clock = clock
        # Recently claimed SMS fingerprints (claim key -> claim time). Every
        # ingestion entry point calls try_claim_sms() before processing, so a
        # message is parsed and persisted exactly once even if the platform
        # delivers the same SMS_RECEIVED broadcast more than once.
        self._recent_sms_claims: "OrderedDict[str, int]" = OrderedDict()
        # Kotlin's @Synchronized: one monitor for try_claim_sms and
        # process_sms. RLock because process_sms -> stop_operation touches
        # the same prefs but must not re-enter this lock... it doesn't take
        # it; RLock kept for safety against future re-entry.
        self._lock = threading.RLock()

    def try_claim_sms(self, body: str) -> bool:
        # Key is body-only: the two pipelines see different sender strings
        # for the same SMS (DLT header vs messaging-app display name), so a
        # sender-qualified key would never dedupe across them.
        key = sms_parser.claim_key(body)
        now = self._clock()
        with self._lock:
            last_claim = self._recent_sms_claims.get(key)
            if last_claim is not None and now - last_claim < SMS_CLAIM_WINDOW_MILLIS:
                return False
            self._recent_sms_claims[key] = now
            self._recent_sms_claims.move_to_end(key)
            while len(self._recent_sms_claims) > _MAX_RECENT_CLAIMS:
                self._recent_sms_claims.popitem(last=False)
            return True

    def start_operation(
        self,
        operation_type: str,
        expected_amount: Optional[str] = None,
        phone_number: Optional[str] = None,
        session_txn_id: Optional[str] = None,
    ) -> None:
        """Start monitoring for a payment operation. session_txn_id is the
        PaymentSessionManager transaction id (the PENDING row's key),
        persisted here so a confirming SMS that arrives AFTER a process
        death — when the in-memory session is gone — can still be matched
        back to its row instead of inserting a duplicate."""
        log.debug("Starting operation: %s", operation_type)
        self._prefs.clear()
        self._prefs.put(KEY_ACTIVE, True)
        self._prefs.put(KEY_START_TIME, self._clock())
        self._prefs.put(KEY_OPERATION_TYPE, operation_type)
        if expected_amount is not None:
            self._prefs.put(KEY_EXPECTED_AMOUNT, expected_amount)
        if phone_number is not None:
            self._prefs.put(KEY_PHONE_NUMBER, phone_number)
        if session_txn_id is not None:
            self._prefs.put(KEY_SESSION_TXN_ID, session_txn_id)

    def stop_operation(self) -> None:
        log.debug("Stopping operation")
        self._prefs.clear()

    def should_process_sms(self) -> bool:
        if not self._prefs.get(KEY_ACTIVE, False):
            return False

        # Check timeout
        start_time = self._prefs.get(KEY_START_TIME, 0)
        elapsed = self._clock() - start_time

        if elapsed > OPERATION_WINDOW_MILLIS:
            log.debug("Operation timed out after %d seconds", elapsed // 1000)
            self.stop_operation()
            return False

        # Additional check: ensure we have an operation type
        operation_type = self._prefs.get(KEY_OPERATION_TYPE)
        if not operation_type:
            self.stop_operation()
            return False

        return True

    def get_operation_type(self) -> Optional[str]:
        return self._prefs.get(KEY_OPERATION_TYPE)

    def get_phone_number(self) -> Optional[str]:
        return self._prefs.get(KEY_PHONE_NUMBER)

    def get_session_txn_id(self) -> Optional[str]:
        """The session transaction id recorded at start_operation, or None.
        Read BEFORE process_sms (which clears the window on a consuming
        match) by callers that need to reattach an orphaned confirmation to
        its row."""
        return self._prefs.get(KEY_SESSION_TXN_ID)

    def process_sms(self, sender: str, body: str) -> Optional[SimpleTransaction]:
        """Synchronized so that when both ingestion pipelines race past
        should_process_sms(), only the first one inside consumes the active
        operation — the second sees it stopped and bails."""
        log.debug("Processing SMS")
        with self._lock:
            # Re-check under lock: the other pipeline may have just consumed
            # the active operation.
            if not self.should_process_sms():
                log.debug("Operation no longer active, skipping")
                return None

            expected_amount = self._prefs.get(KEY_EXPECTED_AMOUNT)
            transaction = sms_parser.parse(sender, body, expected_amount)
            if transaction is None:
                log.debug("SMS did not match a bank transaction")
                return None
            log.debug("Matched %s transaction: %s", transaction.bank_name, transaction.status)

            # Mark operation complete — unless this was an incoming CREDIT. A
            # stray credit must not consume the operation window the real
            # outgoing-debit confirmation may still need.
            if transaction.transaction_type != "CREDIT":
                self.stop_operation()

            return transaction
