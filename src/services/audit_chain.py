"""SHA-256 hash-chained audit trail service.

Public API
----------
ensure_table()          — idempotent CREATE TABLE at startup
log_event(...)          — insert one chained event, return event_id
list_events(limit, offset) — return rows newest-first as list[dict]
verify_chain(skip_legacy)  — walk chain, return verification dict
GENESIS_HASH            — 64-zero anchor for the first event
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg2

# ── Constants ──────────────────────────────────────────────────────────────────

GENESIS_HASH: str = "0" * 64

_DATABASE_URL = os.getenv("DATABASE_URL")
_DB_DSN = (
    f"host={os.getenv('DB_HOST', 'localhost')} "
    f"port={os.getenv('DB_PORT', '5432')} "
    f"dbname={os.getenv('DB_NAME', 'regulens')} "
    f"user={os.getenv('DB_USER', 'postgres')} "
    f"password={os.getenv('DB_PASSWORD', '')}"
)

# ── Internal helpers ───────────────────────────────────────────────────────────


def _get_conn():
    if _DATABASE_URL:
        return psycopg2.connect(_DATABASE_URL, connect_timeout=10)
    return psycopg2.connect(_DB_DSN, connect_timeout=5)


def _compute_hash(data: dict[str, Any], prev_hash: str) -> str:
    payload = json.dumps({**data, "prev_hash": prev_hash}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_prev_hash(cur) -> str:
    cur.execute(
        "SELECT event_hash FROM audit_chain_events ORDER BY created_at DESC LIMIT 1"
    )
    row = cur.fetchone()
    return row[0] if row else GENESIS_HASH


def _row_to_dict(cols: tuple, row: tuple) -> dict[str, Any]:
    d = dict(zip(cols, row))
    d["event_id"] = str(d["event_id"])
    if hasattr(d.get("created_at"), "isoformat"):
        d["created_at"] = d["created_at"].isoformat()
    else:
        d["created_at"] = str(d["created_at"])
    d["event_type"] = d["event_type"] or "query"
    d["prev_hash"] = d["prev_hash"] or GENESIS_HASH
    d["event_hash"] = d["event_hash"] or ""
    return d


_COLS = (
    "event_id", "created_at", "event_type", "persona",
    "query_text", "verdict", "result_count", "avg_confidence",
    "prev_hash", "event_hash",
)

# ── Public API ─────────────────────────────────────────────────────────────────


def ensure_table() -> None:
    """Create audit_chain_events table if it doesn't exist."""
    ddl = """
    CREATE TABLE IF NOT EXISTS audit_chain_events (
        event_id       TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::text,
        created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        event_type     TEXT        NOT NULL DEFAULT 'query',
        persona        TEXT,
        query_text     TEXT,
        verdict        TEXT,
        result_count   INT,
        avg_confidence DOUBLE PRECISION,
        extra_json     JSONB,
        prev_hash      TEXT        NOT NULL,
        event_hash     TEXT        NOT NULL UNIQUE
    );
    CREATE INDEX IF NOT EXISTS ix_audit_chain_created_at
        ON audit_chain_events (created_at DESC);
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(ddl)
        conn.commit()
        cur.close()
    finally:
        conn.close()


def log_event(
    event_type: str,
    persona: str | None = None,
    query_text: str | None = None,
    verdict: str | None = None,
    result_count: int | None = None,
    avg_confidence: float | None = None,
    extra: dict | None = None,
) -> str:
    """Insert one hash-chained audit event. Returns the new event_id."""
    event_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    data: dict[str, Any] = {
        "event_id":       event_id,
        "created_at":     created_at,
        "event_type":     event_type,
        "persona":        persona,
        "query_text":     query_text,
        "verdict":        verdict,
        "result_count":   result_count,
        "avg_confidence": avg_confidence,
    }

    conn = _get_conn()
    try:
        cur = conn.cursor()
        prev_hash = _get_prev_hash(cur)
        event_hash = _compute_hash(data, prev_hash)
        cur.execute(
            """
            INSERT INTO audit_chain_events
                (event_id, created_at, event_type, persona, query_text,
                 verdict, result_count, avg_confidence, extra_json,
                 prev_hash, event_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event_id, created_at, event_type, persona, query_text,
                verdict, result_count, avg_confidence,
                json.dumps(extra) if extra else None,
                prev_hash, event_hash,
            ),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()

    return event_id


def list_events(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """Return audit events newest-first as list of dicts."""
    limit = min(limit, 500)
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT {', '.join(_COLS)} FROM audit_chain_events "
            "ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (limit, offset),
        )
        rows = [_row_to_dict(_COLS, row) for row in cur.fetchall()]
        cur.close()
    finally:
        conn.close()
    return rows


def verify_chain(skip_legacy: bool = True) -> dict[str, Any]:
    """Walk chain oldest→newest, re-derive hashes. Return verification result dict."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT {', '.join(_COLS)} FROM audit_chain_events ORDER BY created_at ASC"
        )
        all_rows = [_row_to_dict(_COLS, row) for row in cur.fetchall()]
        cur.close()
    finally:
        conn.close()

    legacy = [r for r in all_rows if not r["event_hash"]]
    chained = [r for r in all_rows if r["event_hash"]]
    rows = chained if skip_legacy else all_rows
    legacy_skipped = len(legacy) if skip_legacy else 0

    def result(total, valid, broken_id, msg):
        return {
            "total_events": total,
            "legacy_rows_skipped": legacy_skipped,
            "chain_valid": valid,
            "broken_at_event_id": broken_id,
            "message": msg,
        }

    if not rows:
        msg = (
            f"No chained audit events yet. {legacy_skipped} legacy row(s) skipped."
            if legacy_skipped else "No audit events yet."
        )
        return result(0, True, None, msg)

    expected_prev = GENESIS_HASH
    for row in rows:
        eid = row["event_id"]
        if row["prev_hash"] != expected_prev:
            return result(
                len(rows), False, eid,
                f"Chain broken at event {eid}: prev_hash mismatch.",
            )
        data = {k: row[k] for k in (
            "event_id", "created_at", "event_type", "persona",
            "query_text", "verdict", "result_count", "avg_confidence",
        )}
        computed = _compute_hash(data, row["prev_hash"])
        if computed != row["event_hash"]:
            return result(
                len(rows), False, eid,
                f"Chain broken at event {eid}: event_hash mismatch (data tampered).",
            )
        expected_prev = row["event_hash"]

    return result(
        len(rows), True, None,
        f"All {len(rows)} chained event(s) verified. Chain intact. {legacy_skipped} legacy row(s) skipped.",
    )
