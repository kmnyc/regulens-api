"""ReguLens FastAPI backend — semantic search over regulatory_chunks."""

from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Config ─────────────────────────────────────────────────────────────────────

DB_DSN = (
    f"host={os.getenv('DB_HOST', 'localhost')} "
    f"port={os.getenv('DB_PORT', '5432')} "
    f"dbname={os.getenv('DB_NAME', 'regulens')} "
    f"user={os.getenv('DB_USER', 'postgres')} "
    f"password={os.getenv('DB_PASSWORD', '')}"
)

# Prefer DATABASE_URL (Neon / Render) over individual vars
_DATABASE_URL = os.getenv("DATABASE_URL")

PERSONA_THRESHOLDS: dict[str, float] = {
    "Lead Auditor":  0.96,
    "Legal Counsel": 0.96,
    "ML Engineer":   0.88,
}

CONFIDENCE_FLAG = 0.60

# SHA-256 hex string used as prev_hash for the very first audit event
GENESIS_HASH = "0" * 64

# ── Embedding model (ONNX via fastembed — ~150MB RAM, no torch) ────────────────

_embed_model = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _embed_model
    from fastembed import TextEmbedding
    print("Loading all-MiniLM-L6-v2 via fastembed...")
    _embed_model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    # Warm up
    list(_embed_model.embed(["warmup"]))
    print("Model ready.")
    # Create audit table if it doesn't exist yet
    _ensure_audit_table()
    print("Audit table ready.")
    yield


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ReguLens API",
    description="Semantic search over EU AI Act / NIST AI RMF regulatory corpus",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Request / Response models ──────────────────────────────────────────────────


class QueryRequest(BaseModel):
    query: str
    persona: str = "Lead Auditor"


class ChunkResult(BaseModel):
    article_ref: str
    content: str
    similarity: float
    verdict: str
    confidence: float


class QueryResponse(BaseModel):
    results: list[ChunkResult]
    persona: str
    threshold: float
    query: str
    audit_event_id: str | None = None


class AuditEvent(BaseModel):
    id: int
    event_id: str
    created_at: str
    event_type: str
    persona: str | None
    query_text: str | None
    verdict: str | None
    result_count: int | None
    avg_confidence: float | None
    prev_hash: str
    event_hash: str


class AuditVerifyResponse(BaseModel):
    total_events: int
    legacy_rows_skipped: int
    chain_valid: bool
    broken_at_id: int | None
    message: str


# ── DB helpers ─────────────────────────────────────────────────────────────────


def _get_conn():
    if _DATABASE_URL:
        return psycopg2.connect(_DATABASE_URL, connect_timeout=10)
    return psycopg2.connect(DB_DSN, connect_timeout=5)


def _chunk_count() -> int:
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM regulatory_chunks")
        n = cur.fetchone()[0]
        cur.close()
        conn.close()
        return n
    except Exception:
        return -1


def _search(embedding: list[float], limit: int = 5) -> list[dict[str, Any]]:
    emb_str = "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT chunk_id::text,
               article_ref,
               content,
               1 - (embedding <=> %s::vector) AS similarity
        FROM regulatory_chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (emb_str, emb_str, limit),
    )
    cols = ("chunk_id", "article_ref", "content", "similarity")
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


# ── Audit chain helpers ────────────────────────────────────────────────────────


def _ensure_audit_table() -> None:
    """Create audit_events table (or migrate existing) to include all expected columns."""
    statements = [
        # Create table if missing entirely — safe no-op if it exists
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id             BIGSERIAL    PRIMARY KEY,
            event_id       TEXT         NOT NULL DEFAULT gen_random_uuid()::text,
            created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
            event_type     TEXT         NOT NULL DEFAULT 'query',
            persona        TEXT,
            query_text     TEXT,
            verdict        TEXT,
            result_count   INT,
            avg_confidence DOUBLE PRECISION,
            extra_json     JSONB,
            prev_hash      TEXT         NOT NULL DEFAULT '0000000000000000000000000000000000000000000000000000000000000000',
            event_hash     TEXT         NOT NULL DEFAULT ''
        )
        """,
        # Idempotent column migrations — cover any pre-existing table schema
        "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS event_id       TEXT         NOT NULL DEFAULT gen_random_uuid()::text",
        "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS event_type     TEXT         NOT NULL DEFAULT 'query'",
        "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS persona        TEXT",
        "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS query_text     TEXT",
        "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS verdict        TEXT",
        "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS result_count   INT",
        "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS avg_confidence DOUBLE PRECISION",
        "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS extra_json     JSONB",
        "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS prev_hash      TEXT NOT NULL DEFAULT '0000000000000000000000000000000000000000000000000000000000000000'",
        "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS event_hash     TEXT NOT NULL DEFAULT ''",
        # Partial unique index — only enforces uniqueness on real chained rows
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_audit_events_event_hash ON audit_events (event_hash) WHERE event_hash <> ''",
        "CREATE INDEX IF NOT EXISTS ix_audit_events_created_at ON audit_events (created_at DESC)",
    ]
    conn = _get_conn()
    try:
        cur = conn.cursor()
        for stmt in statements:
            try:
                cur.execute(stmt)
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"[audit] DDL warning (non-fatal): {e}")
        cur.close()
    finally:
        conn.close()


def _compute_event_hash(data: dict[str, Any], prev_hash: str) -> str:
    """SHA-256 over deterministic JSON of event fields + prev_hash."""
    payload = json.dumps({**data, "prev_hash": prev_hash}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_prev_hash(cur) -> str:
    """Return the event_hash of the latest chained event, skipping legacy rows (event_hash='')."""
    cur.execute(
        "SELECT event_hash FROM audit_events WHERE event_hash <> '' ORDER BY id DESC LIMIT 1"
    )
    row = cur.fetchone()
    return row[0] if row else GENESIS_HASH


def _log_audit_event(
    event_type: str,
    persona: str | None = None,
    query_text: str | None = None,
    verdict: str | None = None,
    result_count: int | None = None,
    avg_confidence: float | None = None,
    extra: dict | None = None,
) -> str:
    """Insert one hash-chained audit event. Returns the new event_id."""
    import uuid as _uuid
    event_id = str(_uuid.uuid4())
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
        event_hash = _compute_event_hash(data, prev_hash)

        cur.execute(
            """
            INSERT INTO audit_events
                (event_id, created_at, event_type, persona, query_text,
                 verdict, result_count, avg_confidence, extra_json,
                 prev_hash, event_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event_id,
                created_at,
                event_type,
                persona,
                query_text,
                verdict,
                result_count,
                avg_confidence,
                json.dumps(extra) if extra else None,
                prev_hash,
                event_hash,
            ),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()

    return event_id


# ── Routes ─────────────────────────────────────────────────────────────────────


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "chunks_loaded": _chunk_count()}


@app.post("/api/query", response_model=QueryResponse)
def run_query(body: QueryRequest) -> QueryResponse:
    if _embed_model is None:
        raise HTTPException(status_code=503, detail="Model not ready")

    threshold = PERSONA_THRESHOLDS.get(body.persona, 0.96)

    try:
        embedding = _embed(body.query)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Embedding error: {exc}") from exc

    try:
        raw = _search(embedding, limit=5)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB error: {exc}") from exc

    # Keyword boost: if query names "Article N", lift matching chunk similarity
    article_mentions = {
        m.group(0).lower()
        for m in re.finditer(r"article\s+\d+", body.query, re.IGNORECASE)
    }

    results: list[ChunkResult] = []
    for row in raw:
        sim: float = float(row["similarity"])

        # Boost if chunk article_ref matches an explicit article mention in query
        ref_lower = (row["article_ref"] or "").lower()
        if any(mention in ref_lower or ref_lower in mention for mention in article_mentions):
            sim = min(1.0, sim + 0.15)

        # Map raw cosine similarity to confidence:
        # 0.70 → 1.0,  0.66 → 0.96,  0.60 → 0.90,  0.50 → 0.77
        if sim >= 0.60:
            confidence = round(min(1.0, 0.90 + (sim - 0.60) * 1.0), 4)
        elif sim >= 0.45:
            confidence = round(0.70 + (sim - 0.45) * 1.33, 4)
        else:
            confidence = round(sim * 1.2, 4)

        if confidence >= threshold:
            verdict = "PASS"
        elif confidence >= CONFIDENCE_FLAG:
            verdict = "FLAG"
        else:
            verdict = "BLOCK"

        results.append(
            ChunkResult(
                article_ref=row["article_ref"] or "—",
                content=(row["content"] or "")[:400],
                similarity=round(sim, 4),
                verdict=verdict,
                confidence=confidence,
            )
        )

    # Sort by similarity descending after boost
    results.sort(key=lambda r: r.similarity, reverse=True)

    # Determine overall verdict for audit log
    if results:
        overall_verdict = results[0].verdict
        avg_conf = round(sum(r.confidence for r in results) / len(results), 4)
    else:
        overall_verdict = "NO_RESULTS"
        avg_conf = 0.0

    # Log tamper-evident audit event (fire-and-forget; don't fail the query if DB is down)
    audit_event_id: str | None = None
    try:
        audit_event_id = _log_audit_event(
            event_type="query",
            persona=body.persona,
            query_text=body.query[:500],
            verdict=overall_verdict,
            result_count=len(results),
            avg_confidence=avg_conf,
        )
    except Exception as exc:
        print(f"[audit] WARNING: failed to log audit event: {exc}")

    return QueryResponse(
        results=results,
        persona=body.persona,
        threshold=threshold,
        query=body.query,
        audit_event_id=audit_event_id,
    )


@app.get("/api/audit/debug")
def audit_debug() -> dict:
    """Temporary diagnostic endpoint — surfaces DB errors for audit_events."""
    results = {}
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='audit_events' ORDER BY ordinal_position")
        results["columns"] = [{"name": r[0], "type": r[1]} for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*) FROM audit_events")
        results["row_count"] = cur.fetchone()[0]
        cur.close()
        conn.close()
        results["status"] = "ok"
    except Exception as e:
        results["status"] = "error"
        results["error"] = str(e)
    return results


@app.get("/api/audit/events", response_model=list[AuditEvent])
def list_audit_events(limit: int = 50, offset: int = 0) -> list[AuditEvent]:
    """Return audit events in descending order (newest first)."""
    if limit > 500:
        limit = 500
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, event_id, created_at, event_type, persona, query_text,
                   verdict, result_count, avg_confidence, prev_hash, event_hash
            FROM audit_events
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        cols = (
            "id", "event_id", "created_at", "event_type", "persona",
            "query_text", "verdict", "result_count", "avg_confidence",
            "prev_hash", "event_hash",
        )
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        cur.close()
    finally:
        conn.close()

    return [
        AuditEvent(
            id=r["id"],
            event_id=r["event_id"],
            created_at=r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
            event_type=r["event_type"],
            persona=r["persona"],
            query_text=r["query_text"],
            verdict=r["verdict"],
            result_count=r["result_count"],
            avg_confidence=r["avg_confidence"],
            prev_hash=r["prev_hash"],
            event_hash=r["event_hash"],
        )
        for r in rows
    ]


@app.get("/api/audit/verify", response_model=AuditVerifyResponse)
def verify_audit_chain(skip_legacy: bool = True) -> AuditVerifyResponse:
    """Walk the chain oldest→newest and re-derive each hash. Reports first break.

    skip_legacy=true (default): excludes rows with event_hash='' (pre-chain-era rows).
    skip_legacy=false: includes all rows; legacy rows will always fail verification.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, event_id, created_at, event_type, persona, query_text,
                   verdict, result_count, avg_confidence, prev_hash, event_hash
            FROM audit_events
            ORDER BY id ASC
            """
        )
        cols = (
            "id", "event_id", "created_at", "event_type", "persona",
            "query_text", "verdict", "result_count", "avg_confidence",
            "prev_hash", "event_hash",
        )
        all_rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        cur.close()
    finally:
        conn.close()

    legacy = [r for r in all_rows if r["event_hash"] == ""]
    chained = [r for r in all_rows if r["event_hash"] != ""]
    rows = chained if skip_legacy else all_rows
    legacy_skipped = len(legacy) if skip_legacy else 0

    if not rows:
        return AuditVerifyResponse(
            total_events=0,
            legacy_rows_skipped=legacy_skipped,
            chain_valid=True,
            broken_at_id=None,
            message=f"No chained audit events yet. {legacy_skipped} legacy row(s) skipped." if legacy_skipped else "No audit events yet.",
        )

    expected_prev = GENESIS_HASH
    for row in rows:
        if row["prev_hash"] != expected_prev:
            return AuditVerifyResponse(
                total_events=len(rows),
                legacy_rows_skipped=legacy_skipped,
                chain_valid=False,
                broken_at_id=row["id"],
                message=f"Chain broken at event id={row['id']}: prev_hash mismatch.",
            )

        data = {
            "event_id":       row["event_id"],
            "created_at":     row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
            "event_type":     row["event_type"],
            "persona":        row["persona"],
            "query_text":     row["query_text"],
            "verdict":        row["verdict"],
            "result_count":   row["result_count"],
            "avg_confidence": row["avg_confidence"],
        }
        computed = _compute_event_hash(data, row["prev_hash"])
        if computed != row["event_hash"]:
            return AuditVerifyResponse(
                total_events=len(rows),
                legacy_rows_skipped=legacy_skipped,
                chain_valid=False,
                broken_at_id=row["id"],
                message=f"Chain broken at event id={row['id']}: event_hash mismatch (data tampered).",
            )

        expected_prev = row["event_hash"]

    return AuditVerifyResponse(
        total_events=len(rows),
        legacy_rows_skipped=legacy_skipped,
        chain_valid=True,
        broken_at_id=None,
        message=f"All {len(rows)} chained event(s) verified. Chain intact. {legacy_skipped} legacy row(s) skipped.",
    )


# ── Embed helper (defined after model global) ──────────────────────────────────


def _embed(text: str) -> list[float]:
    if _embed_model is None:
        raise RuntimeError("Model not loaded")
    return list(list(_embed_model.embed([text[:512]]))[0])
