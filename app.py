"""ReguLens FastAPI backend — semantic search over regulatory_chunks."""

from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from typing import Any

import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.services.audit_chain import (
    GENESIS_HASH,
    ensure_table as _ensure_audit_table,
    log_event as _log_audit_event,
    list_events as _list_audit_events,
    verify_chain as _verify_audit_chain,
)

# ── Config ─────────────────────────────────────────────────────────────────────

DB_DSN = (
    f"host={os.getenv('DB_HOST', 'localhost')} "
    f"port={os.getenv('DB_PORT', '5432')} "
    f"dbname={os.getenv('DB_NAME', 'regulens')} "
    f"user={os.getenv('DB_USER', 'postgres')} "
    f"password={os.getenv('DB_PASSWORD', '')}"
)

_DATABASE_URL = os.getenv("DATABASE_URL")

PERSONA_THRESHOLDS: dict[str, float] = {
    "Lead Auditor":  0.96,
    "Legal Counsel": 0.96,
    "ML Engineer":   0.88,
}

CONFIDENCE_FLAG = 0.60

# ── Embedding model (ONNX via fastembed — ~150MB RAM, no torch) ────────────────

_embed_model = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _embed_model
    from fastembed import TextEmbedding
    print("Loading all-MiniLM-L6-v2 via fastembed...")
    _embed_model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    list(_embed_model.embed(["warmup"]))
    print("Model ready.")
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
    broken_at_event_id: str | None
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


def _embed(text: str) -> list[float]:
    if _embed_model is None:
        raise RuntimeError("Model not loaded")
    return list(list(_embed_model.embed([text[:512]]))[0])


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

    article_mentions = {
        m.group(0).lower()
        for m in re.finditer(r"article\s+\d+", body.query, re.IGNORECASE)
    }

    results: list[ChunkResult] = []
    for row in raw:
        sim: float = float(row["similarity"])
        ref_lower = (row["article_ref"] or "").lower()
        if any(mention in ref_lower or ref_lower in mention for mention in article_mentions):
            sim = min(1.0, sim + 0.15)

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

    results.sort(key=lambda r: r.similarity, reverse=True)

    if results:
        overall_verdict = results[0].verdict
        avg_conf = round(sum(r.confidence for r in results) / len(results), 4)
    else:
        overall_verdict = "NO_RESULTS"
        avg_conf = 0.0

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


@app.get("/api/audit/events", response_model=list[AuditEvent])
def list_audit_events(limit: int = 50, offset: int = 0) -> list[AuditEvent]:
    """Return audit events in descending order (newest first)."""
    rows = _list_audit_events(limit=limit, offset=offset)
    return [AuditEvent(**r) for r in rows]


@app.get("/api/audit/verify", response_model=AuditVerifyResponse)
def verify_audit_chain(skip_legacy: bool = True) -> AuditVerifyResponse:
    """Walk chain oldest→newest, re-derive hashes, report first break."""
    return AuditVerifyResponse(**_verify_audit_chain(skip_legacy=skip_legacy))
