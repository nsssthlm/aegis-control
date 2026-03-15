"""AEGIS SQLite database — WAL mode, events + AI context storage."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import aiosqlite

_this_dir = os.path.dirname(os.path.abspath(__file__))       # services/
_hub_dir = os.path.dirname(_this_dir)                         # orion-hub/
_project_root = os.path.dirname(_hub_dir)                     # aegis-control/
DB_PATH = os.path.join(_project_root, "aegis.db")

_db: Optional[aiosqlite.Connection] = None


async def init() -> aiosqlite.Connection:
    """Initialize the database, create tables, enable WAL, run cleanup."""
    global _db

    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row

    # Enable WAL mode for concurrent reads
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA synchronous=NORMAL")
    await _db.execute("PRAGMA busy_timeout=5000")

    # Create tables
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            severity TEXT NOT NULL,
            source TEXT NOT NULL,
            env TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT DEFAULT '',
            timestamp TEXT NOT NULL,
            speak INTEGER DEFAULT 0,
            metadata TEXT DEFAULT '{}'
        )
    """)

    await _db.execute("""
        CREATE TABLE IF NOT EXISTS ai_context (
            event_id TEXT PRIMARY KEY,
            analysis TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
        )
    """)

    # Create indexes
    await _db.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)"
    )
    await _db.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity)"
    )
    await _db.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_env ON events(env)"
    )

    await _db.commit()

    # Auto-cleanup: delete events older than 7 days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    cursor = await _db.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))
    deleted = cursor.rowcount
    if deleted > 0:
        # Cascade delete ai_context entries for removed events
        await _db.execute(
            "DELETE FROM ai_context WHERE event_id NOT IN (SELECT id FROM events)"
        )
        await _db.commit()
        print(f"[DATABASE] Cleaned up {deleted} events older than 7 days")

    print(f"[DATABASE] Initialized at {DB_PATH} (WAL mode)")
    return _db


def get_db() -> aiosqlite.Connection:
    """Get the active database connection. Raises if not initialized."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call database.init() first.")
    return _db


async def insert_event(event: dict) -> None:
    """Insert an event into the database."""
    db = get_db()
    metadata_str = json.dumps(event.get("metadata", {}))
    await db.execute(
        """INSERT OR REPLACE INTO events
           (id, type, severity, source, env, title, body, timestamp, speak, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event["id"],
            event["type"],
            event["severity"],
            event["source"],
            event["env"],
            event["title"],
            event.get("body", ""),
            event["timestamp"],
            1 if event.get("speak") else 0,
            metadata_str,
        ),
    )
    await db.commit()


async def get_events(
    env: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[dict]:
    """Query events, newest first. Optional env/severity filter."""
    db = get_db()
    conditions = []
    params: list = []

    if env:
        conditions.append("env = ?")
        params.append(env)
    if severity:
        conditions.append("severity = ?")
        params.append(severity)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM events {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()

    results = []
    for row in rows:
        event = dict(row)
        # Parse metadata back to dict
        if isinstance(event.get("metadata"), str):
            try:
                event["metadata"] = json.loads(event["metadata"])
            except (json.JSONDecodeError, TypeError):
                event["metadata"] = {}
        # Convert speak integer back to boolean
        event["speak"] = bool(event.get("speak"))
        results.append(event)

    return results


async def get_recent_events(limit: int = 10) -> List[dict]:
    """Get the most recent events for AI context injection."""
    return await get_events(limit=limit)


async def get_events_count_by_env_and_severity(
    env: str, hours: int = 24
) -> dict:
    """Get event counts by severity for a given env in the last N hours."""
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    cursor = await db.execute(
        """SELECT severity, COUNT(*) as count FROM events
           WHERE env = ? AND timestamp > ?
           GROUP BY severity""",
        (env, cutoff),
    )
    rows = await cursor.fetchall()
    return {row["severity"]: row["count"] for row in rows}


async def get_last_event_for_env(env: str) -> Optional[dict]:
    """Get the most recent event for a specific environment."""
    events = await get_events(env=env, limit=1)
    return events[0] if events else None


async def insert_ai_context(event_id: str, analysis: str) -> None:
    """Store AI analysis for an event."""
    db = get_db()
    await db.execute(
        "INSERT OR REPLACE INTO ai_context (event_id, analysis, created_at) VALUES (?, ?, ?)",
        (event_id, analysis, datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()


async def close() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
        print("[DATABASE] Connection closed")
