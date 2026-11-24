# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/data/TransactionStatus.kt

"""Transaction status and source constants."""

PENDING = "PENDING"
SUCCESS = "SUCCESS"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
UNVERIFIED = "UNVERIFIED"
NEEDS_REVIEW = "NEEDS_REVIEW"

# Where a transaction record originated.
SOURCE_SMS = "SMS"
SOURCE_MANUAL = "MANUAL"
SOURCE_QR = "QR"
