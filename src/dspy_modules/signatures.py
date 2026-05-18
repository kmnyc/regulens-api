"""DSPy signatures for ReguLens compliance pipeline."""

from __future__ import annotations

import dspy


class PersonaSynthesis(dspy.Signature):
    """Answer a regulatory compliance question grounded in retrieved context.

    You are an AI compliance expert acting in the specified persona role.
    Base your answer ONLY on the provided regulatory context. Cite article
    references precisely. Be concise and authoritative.
    """

    query: str = dspy.InputField(desc="The compliance question to answer")
    persona: str = dspy.InputField(desc="Expert persona: lead_auditor, legal_counsel, or ml_engineer")
    context: str = dspy.InputField(desc="Retrieved regulatory text chunks with article references")

    answer: str = dspy.OutputField(desc="Grounded compliance answer citing specific articles")


class ClaimDecomposition(dspy.Signature):
    """Decompose a compliance answer into discrete verifiable claims.

    Each claim should be a single factual assertion that can be independently
    verified against the regulatory source text. Output one claim per line.
    """

    answer: str = dspy.InputField(desc="The synthesized compliance answer to decompose")
    context: str = dspy.InputField(desc="The regulatory context the answer was grounded in")

    claims: str = dspy.OutputField(
        desc="Newline-separated list of discrete verifiable claims extracted from the answer"
    )
