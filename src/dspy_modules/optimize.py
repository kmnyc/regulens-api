"""DSPy optimization script for ReguLens — MIPROv2 with Opik tracing.

Run locally (requires dspy-ai installed):
    pip3 install dspy-ai
    DEEPSEEK_API_KEY=... GROQ_API_KEY=... python3 src/dspy_modules/optimize.py

LM split:
  - prompt_model (MIPROv2 instruction generation): DeepSeek deepseek-chat
  - task_model (trial eval): DeepSeek deepseek-chat
  - metric: keyword matching against prediction.answer — no live API calls during trials
  - context: prefetched from /api/v1/query (semantic search) before optimization starts

DSPy is not installed on Render free tier — this runs offline only.
Opik traces optimization trials if OPIK_API_KEY is set.
"""

from __future__ import annotations

import os
import sys
import time
import requests

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
    # EU AI Act
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
        "query": "What are the accuracy and robustness requirements under Article 15?",
        "persona": "lead_auditor",
        "expected_verdict": "PASS",
    },
    # NIST AI RMF
    {
        "query": "How does NIST AI RMF define the GOVERN function?",
        "persona": "ml_engineer",
        "expected_verdict": "PASS",
    },
    {
        "query": "How does NIST AI RMF MAP function relate to risk identification?",
        "persona": "ml_engineer",
        "expected_verdict": "PASS",
    },
    {
        "query": "How should AI systems log data for audit trail compliance?",
        "persona": "ml_engineer",
        "expected_verdict": "PASS",
    },
    # ISO 42001
    {
        "query": "What does ISO 42001 Clause 6 require for AI risk assessment?",
        "persona": "lead_auditor",
        "expected_verdict": "PASS",
    },
    {
        "query": "What are the ISO 42001 requirements for AI system impact assessment?",
        "persona": "legal_counsel",
        "expected_verdict": "PASS",
    },
    {
        "query": "How does ISO 42001 Clause 9 define performance evaluation for AI systems?",
        "persona": "ml_engineer",
        "expected_verdict": "PASS",
    },
    {
        "query": "What transparency and explainability obligations does ISO 42001 impose?",
        "persona": "legal_counsel",
        "expected_verdict": "PASS",
    },
    {
        "query": "What human oversight controls does ISO 42001 require for AI systems?",
        "persona": "lead_auditor",
        "expected_verdict": "PASS",
    },
]


# ── Metric ─────────────────────────────────────────────────────────────────────

# Synonym-group keyword map: each entry is a list of slots.
# A slot is a list of synonyms — slot is matched if ANY synonym appears in the answer.
# Score = fraction of slots matched. Each slot tests one distinct concept.
_QUERY_KEYWORDS: dict[str, list[list[str]]] = {
    # EU AI Act
    "article 9":       [["article 9"], ["risk management"], ["high-risk"]],
    "article 13":      [["article 13"], ["transparency"], ["information"]],
    "article 14":      [["article 14"], ["human oversight", "oversight"], ["oversight"]],
    "article 11":      [["article 11"], ["documentation", "documented"], ["technical"]],
    "article 5":       [["article 5"], ["prohibited"], ["unacceptable", "forbidden", "banned", "impermissible"]],
    "article 43":      [["article 43"], ["conformity"], ["assessment"]],
    "article 15":      [["article 15"], ["accuracy"], ["robustness", "resilience", "robust"]],
    # NIST AI RMF
    "govern function": [["govern", "governance"], ["governance", "policy", "policies"], ["accountability", "accountab"]],
    "map function":    [["map"], ["risk"], ["context", "categor"]],
    "audit trail":     [["log", "logging"], ["audit"], ["record", "records", "retain", "track"]],
    # ISO 42001
    "iso 42001 clause 6":    [["iso 42001", "iso/iec 42001", "42001"], ["risk"], ["assessment"]],
    "iso 42001 requirements for ai system impact": [["impact"], ["assessment"], ["iso 42001", "iso/iec 42001", "42001"]],
    "iso 42001 clause 9":    [["iso 42001", "iso/iec 42001", "42001"], ["performance"], ["evaluation", "monitor", "measur"]],
    "transparency and explainability obligations does iso": [["transparency", "transparent"], ["explainab"], ["iso 42001", "iso/iec 42001", "42001"]],
    "human oversight controls does iso 42001": [["oversight", "human oversight"], ["iso 42001", "iso/iec 42001", "42001"], ["control", "mechanism", "require", "oversight"]],
}

# Generic compliance signals — any 1 match from this flat list returns partial score
_GENERIC_KEYWORDS: list[list[str]] = [
    ["article"], ["nist"], ["iso"], ["compliance", "comply"], ["requirement"], ["regulation"]
]


def claim_accuracy_metric(example, prediction, trace=None) -> float:
    """Fraction of concept slots matched in prediction.answer (any synonym per slot)."""
    answer = getattr(prediction, "answer", "") or ""
    if not answer.strip():
        print(f"  metric: empty answer → 0.0")
        return 0.0

    answer_lower = answer.lower()
    query_lower = example["query"].lower()

    slots = next(
        (kws for key, kws in _QUERY_KEYWORDS.items() if key in query_lower),
        _GENERIC_KEYWORDS,
    )

    matched = sum(1 for slot in slots if any(k in answer_lower for k in slot))
    score = round(matched / len(slots), 4)
    print(f"  metric: {matched}/{len(slots)} slots → {score} | '{example['query'][:55]}'")
    return score


# ── DSPy optimization ──────────────────────────────────────────────────────────

def _build_deepseek_lm(dspy):
    """Build DeepSeek LM for MIPROv2 instruction generation. Returns None if key missing."""
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not deepseek_key:
        print("WARNING: DEEPSEEK_API_KEY not set — MIPROv2 will use Groq for instruction generation too.")
        return None
    try:
        lm = dspy.LM(
            model="deepseek/deepseek-chat",
            api_key=deepseek_key,
            api_base="https://api.deepseek.com",
            temperature=0.9,
            max_tokens=2048,
        )
        print("DeepSeek deepseek-chat configured as MIPROv2 prompt_model.")
        return lm
    except Exception as exc:
        print(f"DeepSeek LM init failed (falling back to Groq for instructions): {exc}")
        return None


def _prefetch_contexts(examples: list[dict]) -> list[str]:
    """Fetch real retrieval contexts from live API (/api/v1/query — semantic search, no Groq synthesis)."""
    # Wake the API first
    print(f"Waking live API at {LIVE_API}...")
    try:
        r = requests.get(f"{LIVE_API}/api/health", timeout=30)
        print(f"  API status: {r.json()}")
    except Exception as exc:
        print(f"  WARNING: API wake failed ({exc}) — contexts will be empty")
        return [""] * len(examples)

    contexts = []
    print(f"Prefetching retrieval context for {len(examples)} benchmark examples...")
    for i, ex in enumerate(examples):
        try:
            resp = requests.post(
                f"{LIVE_API}/api/v1/query",
                json={"query": ex["query"], "persona": ex["persona"]},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            chunks = data.get("results", [])
            context = "\n\n".join(
                f"[{c['article_ref']}]: {c['content']}" for c in chunks
            )
            contexts.append(context)
            top_ref = chunks[0]["article_ref"] if chunks else "none"
            print(f"  [{i+1:02d}/{len(examples)}] {len(chunks)} chunks (top: {top_ref}) — {ex['query'][:48]}")
            if i < len(examples) - 1:
                time.sleep(1)
        except Exception as exc:
            print(f"  [{i+1:02d}] fetch failed ({exc}) — using empty context")
            contexts.append("")
    return contexts


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

    # Build DeepSeek LM — use as global so ChainOfThought modules pick it up
    groq_lm = dspy.settings.lm  # fallback if DeepSeek key missing
    deepseek_lm = _build_deepseek_lm(dspy)
    if deepseek_lm is not None:
        dspy.configure(lm=deepseek_lm)  # override global — synthesizer uses DeepSeek during trials
    prompt_model = deepseek_lm if deepseek_lm is not None else groq_lm
    task_model = deepseek_lm if deepseek_lm is not None else groq_lm

    from src.dspy_modules.modules import ReguLensSynthesizer

    lm_name = "DeepSeek deepseek-chat" if deepseek_lm is not None else "Groq llama-3.3-70b-versatile (fallback)"
    print(f"\nRunning MIPROv2 optimization on {len(BENCHMARK_EXAMPLES)} examples...")
    print(f"  prompt_model (instruction gen): {lm_name}")
    print(f"  task_model   (trial eval):      {lm_name}")
    print("Metric uses keyword matching on prediction.answer — no live API calls.\n")

    # Prefetch real retrieval contexts from live API
    contexts = _prefetch_contexts(BENCHMARK_EXAMPLES)

    trainset = [
        dspy.Example(
            query=ex["query"],
            persona=ex["persona"],
            context=ctx,
        ).with_inputs("query", "persona", "context")
        for ex, ctx in zip(BENCHMARK_EXAMPLES, contexts)
    ]

    synthesizer = ReguLensSynthesizer()

    try:
        optimizer = dspy.MIPROv2(
            metric=claim_accuracy_metric,
            prompt_model=prompt_model,
            task_model=task_model,
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

        demos = getattr(getattr(optimized, "synthesize", None), "demos", None) or \
                getattr(getattr(getattr(optimized, "synthesize", None), "predict", None), "demos", None) or []
        print(f"Demos in best program: {len(demos)}")

        save_path = "src/dspy_modules/optimized_synthesizer.json"
        optimized.save(save_path)
        print(f"Optimized program saved to {save_path}")

    except Exception as exc:
        print(f"Optimization error: {exc}")
        print("(Non-fatal — live pipeline unaffected)")


if __name__ == "__main__":
    run_optimization()
