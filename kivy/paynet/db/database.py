# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Flowpay
# Ported from app/src/main/java/com/paynet/app/data/{AppDatabase,TransactionDao}.kt

"""sqlite3-backed transaction store, replacing Room.

Deviations from the Kotlin original, both recorded in MIGRATION.md:
- Room's Flow-returning queries become synchronous list-returning methods;
  the UI layer re-queries on demand. No reactive streams.
- SQLCipher at-rest encryption is a parity risk, not yet carried over; the
  database file here is plaintext sqlite3.

The SQL statements themselves mirror the @Query annotations one to one,
including the lifecycle guards (a confirmation may only land on a PENDING
row; stale PENDING rows are discarded past their deadline).
"""

import sqlite3
import threading
from typing import List, Optional

from paynet import status as txn_status
from paynet.db.models import Transaction

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    transactionId TEXT PRIMARY KEY,
    amount TEXT NOT NULL,
    status TEXT NOT NULL,
    bankName TEXT NOT NULL,
    smsExcerpt TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    upiId TEXT,
    transactionType TEXT NOT NULL,
    recipientName TEXT,
    phoneNumber TEXT,
    bankRef TEXT,
    deadlineAt INTEGER,
    source TEXT,
    verifiedAt INTEGER
);
CREATE INDEX IF NOT EXISTS index_transactions_timestamp ON transactions (timestamp);
CREATE INDEX IF NOT EXISTS index_transactions_status ON transactions (status);
"""

DB_NAME = "paynet_database"
DB_FILE = "paynet_database.db"


class Database:
    """Thread-safe sqlite3 wrapper exposing the TransactionDao surface."""

    def __init__(self, path: str = DB_FILE):
        self._lock = threading.RLock()
        # check_same_thread=False: guarded by the RLock, like Room's pool.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)

    def close(self):
        with self._lock:
            self._conn.close()

    # -- mapping ----------------------------------------------------------

    @staticmethod
    def _row_to_transaction(row: sqlite3.Row) -> Transaction:
        return Transaction(**{col: row[col] for col in Transaction.COLUMNS})

    def _query_all(self, sql: str, params=()) -> List[Transaction]:
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_transaction(row) for row in rows]

    def _execute(self, sql: str, params=()) -> int:
        with self._lock, self._conn:
            cursor = self._conn.execute(sql, params)
            return cursor.rowcount

    # -- queries (1:1 with TransactionDao) --------------------------------

    def get_all_transactions(self) -> List[Transaction]:
        return self._query_all("SELECT * FROM transactions ORDER BY timestamp DESC")

    def get_recent_transactions(self, limit: int = 10) -> List[Transaction]:
        return self._query_all(
            "SELECT * FROM transactions ORDER BY timestamp DESC LIMIT ?", (limit,)
        )

    def get_recent_confirmed_transactions(self, limit: int = 10) -> List[Transaction]:
        """PENDING rows are excluded: a payment in flight has no outcome yet,
        and showing it beside settled ones reads as though it completed."""
        return self._query_all(
            "SELECT * FROM transactions WHERE status != 'PENDING'"
            " ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )

    def get_transactions_by_status(self, status: str) -> List[Transaction]:
        return self._query_all(
            "SELECT * FROM transactions WHERE status = ? ORDER BY timestamp DESC",
            (status,),
        )

    def get_transactions_by_bank(self, bank_name: str) -> List[Transaction]:
        return self._query_all(
            "SELECT * FROM transactions WHERE bankName = ? ORDER BY timestamp DESC",
            (bank_name,),
        )

    def search_transactions(self, query: str) -> List[Transaction]:
        return self._query_all(
            "SELECT * FROM transactions WHERE recipientName LIKE ?"
            " OR phoneNumber LIKE ? ORDER BY timestamp DESC",
            (query, query),
        )

    def get_transaction_by_id(self, transaction_id: str) -> Optional[Transaction]:
        rows = self._query_all(
            "SELECT * FROM transactions WHERE transactionId = ?", (transaction_id,)
        )
        return rows[0] if rows else None

    def insert_transaction(self, transaction: Transaction):
        cols = Transaction.COLUMNS
        sql = (
            f"INSERT OR REPLACE INTO transactions ({', '.join(cols)})"
            f" VALUES ({', '.join('?' for _ in cols)})"
        )
        self._execute(sql, tuple(getattr(transaction, col) for col in cols))

    def insert_transactions(self, transactions: List[Transaction]):
        for transaction in transactions:
            self.insert_transaction(transaction)

    def update_transaction(self, transaction: Transaction):
        cols = Transaction.COLUMNS
        assignments = ", ".join(f"{col} = ?" for col in cols if col != "transactionId")
        values = tuple(
            getattr(transaction, col) for col in cols if col != "transactionId"
        ) + (transaction.transactionId,)
        self._execute(f"UPDATE transactions SET {assignments} WHERE transactionId = ?", values)

    def delete_transaction(self, transaction: Transaction):
        self.delete_transaction_by_id(transaction.transactionId)

    def delete_transaction_by_id(self, transaction_id: str):
        self._execute(
            "DELETE FROM transactions WHERE transactionId = ?", (transaction_id,)
        )

    def delete_all_transactions(self):
        self._execute("DELETE FROM transactions")

    def get_transaction_count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM transactions").fetchone()
        return row[0]

    def get_total_amount(self) -> Optional[float]:
        with self._lock:
            row = self._conn.execute(
                "SELECT SUM(CAST(amount AS REAL)) FROM transactions"
                " WHERE status IN ('SUCCESS', 'SUCCESSFUL', 'COMPLETED')"
            ).fetchone()
        return row[0]

    def get_transactions_by_date_range(
        self, start_time: int, end_time: int
    ) -> List[Transaction]:
        return self._query_all(
            "SELECT * FROM transactions WHERE timestamp BETWEEN ? AND ?"
            " ORDER BY timestamp DESC",
            (start_time, end_time),
        )

    def transition_status(
        self, transaction_id: str, expected_status: str, new_status: str
    ) -> int:
        """Atomically move a row from one lifecycle status to another.
        Returns the number of rows changed (0 if not in the expected status)."""
        return self._execute(
            "UPDATE transactions SET status = ?"
            " WHERE transactionId = ? AND status = ?",
            (new_status, transaction_id, expected_status),
        )

    def confirm_transaction(
        self,
        transaction_id: str,
        status: str,
        bank_ref: Optional[str],
        bank_name: str,
        sms_excerpt: str,
        upi_id: Optional[str],
        recipient_name: Optional[str],
        amount: str,
        verified_at: int,
        expected_status: str = txn_status.PENDING,
    ) -> int:
        """Fill in bank-confirmed details on a session row once the
        confirming SMS arrives. Values the session already knows are never
        erased by a sparser SMS (COALESCE), and amount is filled only when
        the row started without one. expected_status guards which rows a
        confirmation may land on — callers pass PENDING, so an SMS arriving
        after cancellation can never rewrite the cancelled row."""
        return self._execute(
            "UPDATE transactions SET status = ?, bankRef = ?, bankName = ?,"
            " smsExcerpt = ?, upiId = COALESCE(?, upiId),"
            " recipientName = COALESCE(?, recipientName),"
            " amount = CASE WHEN amount = '' THEN ? ELSE amount END,"
            " verifiedAt = ?"
            " WHERE transactionId = ? AND status = ?",
            (
                status,
                bank_ref,
                bank_name,
                sms_excerpt,
                upi_id,
                recipient_name,
                amount,
                verified_at,
                transaction_id,
                expected_status,
            ),
        )

    def delete_stale_pending(self, now: int) -> int:
        """PENDING rows past their verification deadline are discarded: a
        payment with no bank confirmation is not a payment we can report on."""
        return self._execute(
            "DELETE FROM transactions WHERE status = 'PENDING'"
            " AND deadlineAt IS NOT NULL AND deadlineAt < ?",
            (now,),
        )

    def delete_pending(self, transaction_id: str) -> int:
        """Discards one row only while it is still awaiting confirmation —
        the status guard keeps a deadline that fires just as the SMS lands
        from deleting the row that SMS confirmed."""
        return self._execute(
            "DELETE FROM transactions WHERE transactionId = ? AND status = 'PENDING'",
            (transaction_id,),
        )
