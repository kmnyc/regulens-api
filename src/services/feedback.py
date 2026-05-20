"""Feedback events table — stores low-confidence or failing queries for weekly retraining."""

from __future__ import annotations

import os
from typing import Any

import psycopg2

_DATABASE_URL = os.getenv("DATABASE_URL")
_DB_DSN = (
    f"host={os.getenv('DB_HOST', 'localhost')} "
    f"port={os.getenv('DB_PORT', '5432')} "
    f"dbname={os.getenv('DB_NAME', 'regulens')} "
    f"user={os.getenv('DB_USER', 'postgres')} "
    f"password={os.getenv('DB_PASSWORD', '')}"
)


def _get_conn():
    if _DATABASE_URL:
        return psycopg2.connect(_DATABASE_URL, connect_timeout=10)
    return psycopg2.connect(_DB_DSN, connect_timeout=5)


def ensure_table() -> None:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS feedback_events (
                id                SERIAL       PRIMARY KEY,
                query_text        TEXT         NOT NULL,
                persona           TEXT         NOT NULL,
                confidence        DOUBLE PRECISION NOT NULL,
                verdict           TEXT         NOT NULL,
                created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
                used_for_training BOOLEAN      NOT NULL DEFAULT FALSE
            );
            CREATE INDEX IF NOT EXISTS ix_feedback_events_unused
                ON feedback_events (used_for_training, created_at DESC)
                WHERE NOT used_for_training;
        """)
        conn.commit()
        cur.close()
    finally:
        conn.close()


def log_event(query_text: str, persona: str, confidence: float, verdict: str) -> None:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO feedback_events (query_text, persona, confidence, verdict)"
            " VALUES (%s, %s, %s, %s)",
            (query_text[:500], persona, confidence, verdict),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def get_unused_events(limit: int = 50) -> list[dict[str, Any]]:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, query_text, persona, confidence, verdict"
            " FROM feedback_events"
            " WHERE NOT used_for_training"
            " ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
        cols = ("id", "query_text", "persona", "confidence", "verdict")
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        cur.close()
    finally:
        conn.close()
    return rows


def mark_used(ids: list[int]) -> None:
    if not ids:
        return
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE feedback_events SET used_for_training = TRUE WHERE id = ANY(%s)",
            (ids,),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()
