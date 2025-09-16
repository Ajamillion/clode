"""Persistence helpers for optimization runs."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "gateway.db"
VALID_STATUSES = {"queued", "running", "succeeded", "failed"}


@dataclass(slots=True)
class RunRecord:
    """Represents a persisted optimisation run."""

    id: str
    status: str
    created_at: float
    updated_at: float
    params: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "params": self.params,
            "result": self.result,
            "error": self.error,
        }


class RunStore:
    """Lightweight SQLite-backed store for optimisation runs."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = Path(db_path) if db_path else DEFAULT_DB_PATH
        parent = self._path.parent
        if str(parent) not in {"", "."} and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self._path), timeout=30, isolation_level=None, check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    params TEXT NOT NULL,
                    result TEXT,
                    error TEXT
                )
                """
            )

    def create_run(self, params: dict[str, Any]) -> RunRecord:
        now = time.time()
        run_id = uuid.uuid4().hex
        record = RunRecord(
            id=run_id,
            status="queued",
            created_at=now,
            updated_at=now,
            params=dict(params),
            result=None,
            error=None,
        )
        payload = (run_id, record.status, now, now, json.dumps(record.params), None, None)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO runs (id, status, created_at, updated_at, params, result, error) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    payload,
                )
        return record

    def mark_running(self, run_id: str) -> None:
        self._update_status(run_id, "running", result=None, error=None)

    def complete_run(self, run_id: str, result: dict[str, Any]) -> None:
        self._update_status(run_id, "succeeded", result=result, error=None)

    def mark_failed(self, run_id: str, error: str) -> None:
        self._update_status(run_id, "failed", result=None, error=error)

    def _update_status(
        self,
        run_id: str,
        status: str,
        *,
        result: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        now = time.time()
        result_json = json.dumps(result) if result is not None else None
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    "UPDATE runs SET status = ?, updated_at = ?, result = ?, error = ? WHERE id = ?",
                    (status, now, result_json, error, run_id),
                )
                if cursor.rowcount == 0:
                    raise KeyError(f"Unknown run id: {run_id}")

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_runs(self, *, limit: int = 20, status: str | None = None) -> list[RunRecord]:
        if status is not None and status not in VALID_STATUSES:
            raise ValueError(f"Unsupported status filter: {status}")

        params: list[Any] = []
        query = "SELECT * FROM runs"
        if status is not None:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(limit, 1))

        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_record(row) for row in rows]

    def status_counts(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as count FROM runs GROUP BY status"
            ).fetchall()
        counts: dict[str, int] = {status: 0 for status in VALID_STATUSES}
        for row in rows:
            counts[row["status"]] = int(row["count"])
        return counts

    def delete_all(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM runs")

    def _row_to_record(self, row: sqlite3.Row) -> RunRecord:
        params = json.loads(row["params"]) if row["params"] else {}
        result = json.loads(row["result"]) if row["result"] else None
        error = row["error"] if row["error"] else None
        return RunRecord(
            id=row["id"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            params=params,
            result=result,
            error=error,
        )


__all__ = ["RunStore", "RunRecord"]
