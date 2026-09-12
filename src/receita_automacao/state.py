from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Iterable

from .models import CompanyRecord, EntityType


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    source_key TEXT PRIMARY KEY,
                    row_number INTEGER NOT NULL,
                    company_name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    identifier TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    portal_result TEXT,
                    report_path TEXT,
                    processed_at TEXT,
                    excel_synced INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT,
                    error_message TEXT,
                    started_at TEXT,
                    finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS control (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT OR IGNORE INTO control(key, value) VALUES('command', 'run');
                """
            )
            conn.execute("UPDATE jobs SET status='queued' WHERE status='running'")

    def register(self, records: Iterable[CompanyRecord]) -> None:
        with self.connect() as conn:
            for record in records:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO jobs(
                        source_key, row_number, company_name, entity_type, identifier
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        record.source_key,
                        record.row_number,
                        record.company_name,
                        record.entity_type.value,
                        record.identifier,
                    ),
                )

    def requeue_failed(self) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE jobs SET status='queued', error_code=NULL, error_message=NULL WHERE status='failed'"
            )
            return int(cursor.rowcount)

    def pending(self, limit: int | None = None) -> list[CompanyRecord]:
        sql = "SELECT * FROM jobs WHERE status='queued' ORDER BY row_number"
        params: tuple[object, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            CompanyRecord(
                source_key=row["source_key"],
                row_number=row["row_number"],
                company_name=row["company_name"],
                entity_type=EntityType(row["entity_type"]),
                identifier=row["identifier"],
            )
            for row in rows
        ]

    def mark_started(self, source_key: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE jobs SET status='running', started_at=?, error_code=NULL, error_message=NULL WHERE source_key=?",
                (now_iso(), source_key),
            )

    def mark_result(self, source_key: str, portal_result: str, report_path: str | None) -> str:
        processed_at = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                   SET status='completed', portal_result=?, report_path=?, processed_at=?,
                       finished_at=?, excel_synced=0, error_code=NULL, error_message=NULL
                 WHERE source_key=?
                """,
                (portal_result, report_path, processed_at, processed_at, source_key),
            )
        return processed_at

    def mark_excel_synced(self, source_key: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE jobs SET excel_synced=1 WHERE source_key=?", (source_key,))

    def mark_failed(self, source_key: str, code: str, message: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs SET status='failed', error_code=?, error_message=?, finished_at=?
                 WHERE source_key=?
                """,
                (code, message, now_iso(), source_key),
            )

    def unsynced_completed(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM jobs WHERE status='completed' AND excel_synced=0 ORDER BY row_number"
            ).fetchall()

    def set_control(self, command: str) -> None:
        if command not in {"run", "pause", "stop"}:
            raise ValueError(f"Comando inválido: {command}")
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO control(key, value) VALUES('command', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (command,),
            )

    def get_control(self) -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM control WHERE key='command'").fetchone()
        return "run" if row is None else str(row["value"])

    def summary(self) -> dict[str, int | str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT status, COUNT(*) AS total FROM jobs GROUP BY status").fetchall()
        result: dict[str, int | str] = {row["status"]: row["total"] for row in rows}
        result["control"] = self.get_control()
        return result
