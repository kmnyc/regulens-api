"""Weekly self-improvement retrain script for ReguLens.

Called by GitHub Actions every Monday 00:00 UTC.

Flow:
  1. Load unused feedback_events from Neon (low-conf or non-PASS queries)
  2. Merge with BENCHMARK_EXAMPLES from optimize.py
  3. Prefetch retrieval contexts from live API
  4. Score current optimized_synthesizer.json
  5. Run MIPROv2 with DeepSeek to produce new synthesizer
  6. Score new synthesizer on combined trainset
  7. Quality gate: save new json ONLY if new_score >= current_score
  8. Mark used feedback events as used_for_training=True

Rollback: git checkout pre-self-improvement -- src/dspy_modules/optimized_synthesizer.json
"""

from __future__ import annotations

import os
import sys


def _score_program(synthesizer, trainset, metric) -> float:
    """Run synthesizer on trainset, return mean metric score."""
    import dspy  # noqa: F401 — ensure dspy available before calling
    scores: list[float] = []
    for ex in trainset:
        try:
            pred = synthesizer(query=ex["query"], persona=ex["persona"], context=ex.get("context", ""))
            score = metric(ex, pred)
            scores.append(score)
        except Exception as exc:
            print(f"  [score] error on '{ex['query'][:40]}': {exc}")
            scores.append(0.0)
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def main() -> None:
    try:
        import dspy
    except ImportError:
        print("ERROR: dspy-ai not installed. Run: pip install dspy-ai")
        sys.exit(1)

    from src.services.feedback import get_unused_events, mark_used
    from src.dspy_modules.optimize import (
        BENCHMARK_EXAMPLES,
        claim_accuracy_metric,
        _prefetch_contexts,
        _build_deepseek_lm,
    )
    from src.dspy_config import configure_dspy
    from src.dspy_modules.modules import ReguLensSynthesizer

    if not configure_dspy():
        print("ERROR: GROQ_API_KEY not set — cannot run MIPROv2.")
        sys.exit(1)

    # 1. Load feedback events
    print("\n── Step 1: Loading unused feedback events ──────────────────")
    feedback = get_unused_events(limit=50)
    print(f"  {len(feedback)} unused feedback event(s).")

    feedback_examples = [
        {
            "query": f["query_text"],
            "persona": f["persona"],
            "expected_verdict": f["verdict"],
        }
        for f in feedback
    ]

    # 2. Merge: feedback first (failing/low-conf cases = highest signal), then benchmarks
    all_examples = feedback_examples + BENCHMARK_EXAMPLES
    print(f"  Combined trainset: {len(all_examples)} examples "
          f"({len(feedback_examples)} feedback + {len(BENCHMARK_EXAMPLES)} benchmark).")

    # 3. Prefetch retrieval contexts from live API
    print("\n── Step 2: Prefetching retrieval contexts ───────────────────")
    contexts = _prefetch_contexts(all_examples)

    trainset = [
        dspy.Example(
            query=ex["query"],
            persona=ex["persona"],
            context=ctx,
        ).with_inputs("query", "persona", "context")
        for ex, ctx in zip(all_examples, contexts)
    ]

    opt_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "dspy_modules", "optimized_synthesizer.json")
    )

    # 4. Score current synthesizer
    print("\n── Step 3: Scoring current synthesizer ─────────────────────")
    current_synthesizer = ReguLensSynthesizer()
    current_score = 0.0
    if os.path.exists(opt_path):
        try:
            current_synthesizer.load(opt_path)
            current_score = _score_program(current_synthesizer, trainset, claim_accuracy_metric)
            print(f"  Current score: {current_score:.4f} ({opt_path})")
        except Exception as exc:
            print(f"  WARNING: could not score current synthesizer ({exc}) — treating as 0.0")
    else:
        print(f"  No existing synthesizer at {opt_path} — treating current score as 0.0")

    # 5. Run MIPROv2
    print("\n── Step 4: Running MIPROv2 optimization ────────────────────")
    groq_lm = dspy.settings.lm
    deepseek_lm = _build_deepseek_lm(dspy)
    if deepseek_lm is not None:
        dspy.configure(lm=deepseek_lm)
    prompt_model = deepseek_lm if deepseek_lm is not None else groq_lm
    task_model = deepseek_lm if deepseek_lm is not None else groq_lm
    lm_name = "DeepSeek deepseek-chat" if deepseek_lm is not None else "Groq llama-3.3-70b-versatile"
    print(f"  LM: {lm_name} | trainset: {len(trainset)} examples")

    new_synthesizer = ReguLensSynthesizer()
    try:
        optimizer = dspy.MIPROv2(
            metric=claim_accuracy_metric,
            prompt_model=prompt_model,
            task_model=task_model,
            auto="light",
            num_threads=1,
        )
        optimized = optimizer.compile(
            new_synthesizer,
            trainset=trainset,
            minibatch=False,
            requires_permission_to_run=False,
        )
        print("  Optimization complete.")
    except Exception as exc:
        print(f"  Optimization error: {exc}")
        print("  Keeping existing synthesizer. No changes committed.")
        sys.exit(0)

    # 6. Score new synthesizer
    print("\n── Step 5: Scoring new synthesizer ─────────────────────────")
    new_score = _score_program(optimized, trainset, claim_accuracy_metric)
    print(f"  New score:     {new_score:.4f}")
    print(f"  Current score: {current_score:.4f}")

    # 7. Quality gate
    print("\n── Step 6: Quality gate ─────────────────────────────────────")
    if new_score >= current_score:
        optimized.save(opt_path)
        print(f"  PASSED ({new_score:.4f} >= {current_score:.4f}). Saved new synthesizer.")

        # 8. Mark feedback events as used
        feedback_ids = [f["id"] for f in feedback]
        if feedback_ids:
            mark_used(feedback_ids)
            print(f"  Marked {len(feedback_ids)} feedback event(s) as used_for_training=True.")
    else:
        print(f"  FAILED ({new_score:.4f} < {current_score:.4f}). Keeping existing synthesizer.")

    print("\nDone.")


if __name__ == "__main__":
    main()
