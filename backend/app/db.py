from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "data" / "tasks.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                mode TEXT NOT NULL,
                pipeline_id TEXT,
                image_count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                output_path TEXT,
                error TEXT
            )
            """
        )
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
        }
        if "pipeline_id" not in columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN pipeline_id TEXT")
        conn.commit()


def mark_incomplete_tasks_interrupted(statuses: Iterable[str] = ("Pending", "Running")) -> int:
    status_list = list(statuses)
    if not status_list:
        return 0

    placeholders = ",".join("?" for _ in status_list)
    with get_conn() as conn:
        cursor = conn.execute(
            f"""
            UPDATE tasks
            SET status = ?,
                error = COALESCE(error, ?),
                updated_at = ?
            WHERE status IN ({placeholders})
            """,
            (
                "Interrupted",
                "Task interrupted by server restart",
                _utc_now(),
                *status_list,
            ),
        )
        conn.commit()
        return cursor.rowcount


def create_task(task_id: str, mode: str, image_count: int, pipeline_id: str | None = None) -> Dict[str, Any]:
    now = _utc_now()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, status, mode, pipeline_id, image_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, "Pending", mode, pipeline_id, image_count, now, now),
        )
        conn.commit()
    return get_task(task_id) or {}


def update_task(
    task_id: str,
    status: str,
    output_path: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE tasks
            SET status = ?, output_path = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, output_path, error, _utc_now(), task_id),
        )
        conn.commit()


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def list_tasks(limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]
