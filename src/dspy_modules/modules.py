"""DSPy modules for ReguLens — ChainOfThought wrappers around signatures."""

from __future__ import annotations

import dspy

from src.dspy_modules.signatures import PersonaSynthesis, ClaimDecomposition


class ReguLensSynthesizer(dspy.Module):
    """Agent II: persona-aware synthesis using ChainOfThought reasoning."""

    def __init__(self):
        super().__init__()
        self.synthesize = dspy.ChainOfThought(PersonaSynthesis)

    def forward(self, query: str, persona: str, context: str) -> dspy.Prediction:
        return self.synthesize(query=query, persona=persona, context=context)


class ReguLensDecomposer(dspy.Module):
    """Agent III: claim decomposition using ChainOfThought reasoning."""

    def __init__(self):
        super().__init__()
        self.decompose = dspy.ChainOfThought(ClaimDecomposition)

    def forward(self, answer: str, context: str) -> list[str]:
        result = self.decompose(answer=answer, context=context)
        raw = result.claims or ""
        claims = [c.strip() for c in raw.splitlines() if c.strip()]
        return claims
