"""DSPy configuration for ReguLens — Groq primary, graceful degradation if unavailable."""

from __future__ import annotations

import os


def configure_dspy() -> bool:
    """Configure DSPy with Groq LM. Return True if configured successfully."""
    try:
        import dspy

        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            print("DSPy: GROQ_API_KEY not set — DSPy disabled.")
            return False

        lm = dspy.LM(
            model="groq/llama-3.3-70b-versatile",
            api_key=api_key,
            temperature=0.1,
            max_tokens=600,
        )
        dspy.configure(lm=lm)
        print("DSPy configured with Groq llama-3.3-70b-versatile.")
        return True

    except Exception as exc:
        print(f"DSPy configuration failed (non-fatal): {exc}")
        return False
