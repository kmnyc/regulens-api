"""Pydantic state model for LangGraph pipeline."""

from __future__ import annotations

from pydantic import BaseModel


class PipelineState(BaseModel):
    query: str
    persona: str
    threshold: float = 0.0
    retrieved_chunks: list[dict] = []
    retrieval_count: int = 0
    raw_answer: str = ""
    claims: list[dict] = []
    overall_verdict: str = ""
    avg_confidence: float = 0.0
    failure_count: int = 0
    retry_count: int = 0
    audit_hashes: list[str] = []
