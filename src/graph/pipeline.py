"""LangGraph StateGraph pipeline for ReguLens tri-agent workflow.

Graph topology:
    set_threshold → retrieve → synthesize → verify
                                               ↓
                       respond ← [route] → retry_retrieve → synthesize
                                   ↓
                               gap_report → respond → END

Routing rules:
    < 30% BLOCK  → respond
    30–50% BLOCK + retry < 2 → retry_retrieve
    > 50% BLOCK  → gap_report
"""

from __future__ import annotations

import os
import re
from typing import Any, TypedDict

import psycopg2
import requests
from langgraph.graph import StateGraph, END

# Opik tracing — gracefully degrade if not installed or key missing
try:
    from opik import track as opik_track
    from opik.integrations.langchain import track_langgraph
    _OPIK_AVAILABLE = True
except Exception:
    _OPIK_AVAILABLE = False
    def opik_track(*args, **kwargs):  # type: ignore[misc]
        def decorator(func): return func
        if args and callable(args[0]): return args[0]
        return decorator
    def track_langgraph(graph): return graph  # type: ignore[misc]


class GraphState(TypedDict, total=False):
    query: str
    persona: str
    threshold: float
    retrieved_chunks: list
    retrieval_count: int
    raw_answer: str
    claims: list
    overall_verdict: str
    avg_confidence: float
    failure_count: int
    retry_count: int
    audit_hashes: list

# ── Config ─────────────────────────────────────────────────────────────────────

PERSONA_THRESHOLDS: dict[str, float] = {
    "lead_auditor": 0.96,
    "legal_counsel": 0.96,
    "ml_engineer": 0.88,
}
CONFIDENCE_FLAG = 0.60

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

_DATABASE_URL = os.getenv("DATABASE_URL")
_DB_DSN = (
    f"host={os.getenv('DB_HOST', 'localhost')} "
    f"port={os.getenv('DB_PORT', '5432')} "
    f"dbname={os.getenv('DB_NAME', 'regulens')} "
    f"user={os.getenv('DB_USER', 'postgres')} "
    f"password={os.getenv('DB_PASSWORD', '')}"
)

# Injected at startup by app.py via init_embed_model()
_embed_model = None

# ── Init ───────────────────────────────────────────────────────────────────────


def init_embed_model(model) -> None:
    global _embed_model
    _embed_model = model


# ── Low-level helpers (copied from app.py — no import cycle) ───────────────────


def _get_conn():
    if _DATABASE_URL:
        return psycopg2.connect(_DATABASE_URL, connect_timeout=10)
    return psycopg2.connect(_DB_DSN, connect_timeout=5)


@opik_track(name="embed_query")
def _embed(text: str) -> list[float]:
    if _embed_model is None:
        raise RuntimeError("Embedding model not initialized in graph pipeline")
    return list(list(_embed_model.embed([text[:512]]))[0])


@opik_track(name="search_corpus")
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


@opik_track(name="call_groq_llm")
def _call_groq(query: str, context: str, persona: str) -> str:
    if not GROQ_API_KEY:
        return "[Synthesis unavailable — GROQ_API_KEY not configured]"
    persona_label = persona.replace("_", " ").title()
    system = (
        f"You are a {persona_label} AI compliance expert. "
        "Answer based ONLY on the provided regulatory context. "
        "Cite article references precisely."
    )
    user = f"Regulatory Context:\n{context}\n\nCompliance Question: {query}"
    try:
        resp = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.1,
                "max_tokens": 600,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        return f"[Synthesis error: {exc}]"


# ── Node functions ─────────────────────────────────────────────────────────────


def set_threshold(state: dict) -> dict:
    persona_key = state.get("persona", "lead_auditor").lower().replace(" ", "_")
    return {"threshold": PERSONA_THRESHOLDS.get(persona_key, 0.96)}


def retrieve_node(state: dict) -> dict:
    query = state["query"]
    threshold = state.get("threshold", 0.96)

    embedding = _embed(query)
    raw = _search(embedding, limit=5)

    article_mentions = {
        m.group(0).lower()
        for m in re.finditer(r"article\s+\d+", query, re.IGNORECASE)
    }

    chunks: list[dict] = []
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

        chunks.append({
            "chunk_id": row["chunk_id"],
            "article_ref": row["article_ref"] or "—",
            "content": (row["content"] or "")[:400],
            "similarity": round(sim, 4),
            "confidence": confidence,
            "verdict": verdict,
        })

    chunks.sort(key=lambda r: r["similarity"], reverse=True)
    avg_conf = round(sum(c["confidence"] for c in chunks) / len(chunks), 4) if chunks else 0.0

    return {
        "retrieved_chunks": chunks,
        "retrieval_count": len(chunks),
        "avg_confidence": avg_conf,
    }


def synthesize_node(state: dict) -> dict:
    chunks = state.get("retrieved_chunks", [])
    query = state["query"]
    persona = state.get("persona", "lead_auditor")

    context = "\n\n".join(f"[{c['article_ref']}]: {c['content']}" for c in chunks)
    answer = _call_groq(query, context, persona)
    return {"raw_answer": answer}


def verify_node(state: dict) -> dict:
    chunks = state.get("retrieved_chunks", [])
    failure_count = sum(1 for c in chunks if c["verdict"] == "BLOCK")
    overall_verdict = chunks[0]["verdict"] if chunks else "NO_RESULTS"
    claims = [
        {
            "article_ref": c["article_ref"],
            "verdict": c["verdict"],
            "confidence": c["confidence"],
        }
        for c in chunks
    ]
    return {
        "claims": claims,
        "failure_count": failure_count,
        "overall_verdict": overall_verdict,
    }


def route_after_verify(state: dict) -> str:
    chunks = state.get("retrieved_chunks", [])
    failure_count = state.get("failure_count", 0)
    retry_count = state.get("retry_count", 0)

    if not chunks:
        return "gap_report"

    failure_ratio = failure_count / len(chunks)
    if failure_ratio < 0.30:
        return "respond"
    elif failure_ratio <= 0.50 and retry_count < 2:
        return "retry_retrieve"
    else:
        return "gap_report"


def retry_retrieve(state: dict) -> dict:
    return {"retry_count": state.get("retry_count", 0) + 1}


def gap_report_node(state: dict) -> dict:
    existing = state.get("raw_answer", "")
    note = "[COMPLIANCE GAP: Insufficient regulatory coverage found for this query.]"
    return {
        "overall_verdict": "GAP_REPORT",
        "raw_answer": f"{existing}\n\n{note}".strip() if existing else note,
    }


def respond_node(state: dict) -> dict:
    from src.services.audit_chain import log_event

    audit_event_id: str | None = None
    try:
        audit_event_id = log_event(
            event_type="langgraph_query",
            persona=state.get("persona"),
            query_text=(state.get("query") or "")[:500],
            verdict=state.get("overall_verdict"),
            result_count=state.get("retrieval_count"),
            avg_confidence=state.get("avg_confidence"),
            extra={
                "retry_count": state.get("retry_count", 0),
                "source": "v2",
            },
        )
    except Exception as exc:
        print(f"[audit] WARNING: {exc}")

    return {"audit_hashes": [audit_event_id] if audit_event_id else []}


# ── Graph construction ─────────────────────────────────────────────────────────


def build_regulens_graph():
    graph = StateGraph(GraphState)

    graph.add_node("set_threshold", set_threshold)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("verify", verify_node)
    graph.add_node("retry_retrieve", retry_retrieve)
    graph.add_node("gap_report", gap_report_node)
    graph.add_node("respond", respond_node)

    graph.set_entry_point("set_threshold")

    graph.add_edge("set_threshold", "retrieve")
    graph.add_edge("retrieve", "synthesize")
    graph.add_edge("synthesize", "verify")
    graph.add_conditional_edges(
        "verify",
        route_after_verify,
        {
            "respond": "respond",
            "retry_retrieve": "retry_retrieve",
            "gap_report": "gap_report",
        },
    )
    graph.add_edge("retry_retrieve", "synthesize")
    graph.add_edge("gap_report", "respond")
    graph.add_edge("respond", END)

    compiled = graph.compile()
    try:
        tracked = track_langgraph(compiled)
        print("LangGraph Opik tracing enabled.")
        return tracked
    except Exception as e:
        print(f"Opik tracing failed (non-fatal), using untracked graph: {e}")
        return compiled
