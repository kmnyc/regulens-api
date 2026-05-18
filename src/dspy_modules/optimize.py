"""DSPy optimization script for ReguLens — MIPROv2 with Opik tracing.

Run locally (requires dspy-ai installed):
    pip3 install dspy-ai
    python3 src/dspy_modules/optimize.py

DSPy is not installed on Render free tier — this runs offline only.
Opik traces optimization trials if OPIK_API_KEY is set.
"""

from __future__ import annotations

import os
import sys

LIVE_API = "https://regulens-api-bnlw.onrender.com"

# ── Opik tracing setup ─────────────────────────────────────────────────────────

def _configure_opik():
    try:
        import opik
        opik.configure(
            api_key=os.getenv("OPIK_API_KEY"),
            workspace=os.getenv("OPIK_WORKSPACE"),
        )
        print("Opik configured for optimization tracing.")
        return True
    except Exception as exc:
        print(f"Opik not available (non-fatal): {exc}")
        return False


def track_dspy():
    """Register OpikCallback with DSPy for tracing."""
    try:
        import dspy
        from opik.integrations.dspy import OpikCallback
        cb = OpikCallback(project_name="regulens")
        dspy.settings.configure(callbacks=[cb])
        print("DSPy Opik tracing enabled (OpikCallback).")
    except Exception as exc:
        print(f"DSPy Opik tracing unavailable (non-fatal): {exc}")


# ── Benchmark examples ─────────────────────────────────────────────────────────

BENCHMARK_EXAMPLES = [
    {
        "query": "What does EU AI Act Article 9 require for high-risk AI systems?",
        "persona": "lead_auditor",
        "expected_verdict": "PASS",
    },
    {
        "query": "What are the transparency obligations under EU AI Act Article 13?",
        "persona": "legal_counsel",
        "expected_verdict": "PASS",
    },
    {
        "query": "How does NIST AI RMF define the GOVERN function?",
        "persona": "ml_engineer",
        "expected_verdict": "PASS",
    },
    {
        "query": "What human oversight requirements apply to high-risk AI under Article 14?",
        "persona": "lead_auditor",
        "expected_verdict": "PASS",
    },
    {
        "query": "What technical documentation must providers maintain under Article 11?",
        "persona": "legal_counsel",
        "expected_verdict": "PASS",
    },
    {
        "query": "How does NIST AI RMF MAP function relate to risk identification?",
        "persona": "ml_engineer",
        "expected_verdict": "PASS",
    },
    {
        "query": "What are prohibited AI practices under Article 5 of the EU AI Act?",
        "persona": "lead_auditor",
        "expected_verdict": "PASS",
    },
    {
        "query": "What conformity assessment procedures apply under Article 43?",
        "persona": "legal_counsel",
        "expected_verdict": "PASS",
    },
    {
        "query": "How should AI systems log data for audit trail compliance?",
        "persona": "ml_engineer",
        "expected_verdict": "PASS",
    },
    {
        "query": "What are the accuracy and robustness requirements under Article 15?",
        "persona": "lead_auditor",
        "expected_verdict": "PASS",
    },
]


# ── Metric ─────────────────────────────────────────────────────────────────────

def claim_accuracy_metric(example, prediction, trace=None) -> float:
    """Fraction of PASS verdicts in retrieved chunks."""
    import time
    import requests

    time.sleep(5)  # Groq free tier TPM limit — 12k TPM, space out calls
    try:
        resp = requests.post(
            f"{LIVE_API}/api/v2/query",
            json={"query": example["query"], "persona": example["persona"]},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        claims = data.get("claims", [])
        if not claims:
            return 0.0
        passed = sum(1 for c in claims if c.get("verdict") == "PASS")
        score = round(passed / len(claims), 4)
        print(f"  metric: {passed}/{len(claims)} PASS → {score}")
        return score
    except Exception as exc:
        print(f"  metric error: {exc}")
        return 0.0


# ── DSPy optimization ──────────────────────────────────────────────────────────

def run_optimization():
    try:
        import dspy
    except ImportError:
        print("ERROR: dspy-ai not installed. Run: pip3 install dspy-ai")
        sys.exit(1)

    _configure_opik()
    track_dspy()

    from src.dspy_config import configure_dspy
    if not configure_dspy():
        print("ERROR: GROQ_API_KEY not set. Cannot run optimization.")
        sys.exit(1)

    from src.dspy_modules.modules import ReguLensSynthesizer

    print(f"\nRunning MIPROv2 optimization on {len(BENCHMARK_EXAMPLES)} examples...")
    print("This calls the LIVE API and takes 5-10 minutes.\n")

    trainset = [
        dspy.Example(
            query=ex["query"],
            persona=ex["persona"],
            context="",  # filled at runtime by retrieve step
        ).with_inputs("query", "persona", "context")
        for ex in BENCHMARK_EXAMPLES
    ]

    synthesizer = ReguLensSynthesizer()

    try:
        optimizer = dspy.MIPROv2(
            metric=claim_accuracy_metric,
            auto="light",
            num_threads=1,
        )
        optimized = optimizer.compile(
            synthesizer,
            trainset=trainset,
            minibatch=False,
            requires_permission_to_run=False,
        )
        print("\nOptimization complete.")

        save_path = "src/dspy_modules/optimized_synthesizer.json"
        optimized.save(save_path)
        print(f"Optimized program saved to {save_path}")

    except Exception as exc:
        print(f"Optimization error: {exc}")
        print("(Non-fatal — live pipeline unaffected)")


if __name__ == "__main__":
    run_optimization()
