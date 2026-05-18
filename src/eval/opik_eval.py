"""Opik evaluation dataset and runner for ReguLens compliance pipeline.

Calls the LIVE API. Run locally:
    python3 src/eval/opik_eval.py

Creates/updates dataset 'regulens-benchmarks' in Opik project 'regulens'.
Opik API key must be set: export OPIK_API_KEY=...
"""

from __future__ import annotations

import os

import requests

LIVE_API = "https://regulens-api-bnlw.onrender.com"

# ── Benchmark dataset items ────────────────────────────────────────────────────

BENCHMARK_ITEMS = [
    {
        "input": {
            "query": "What does EU AI Act Article 9 require for high-risk AI systems?",
            "persona": "lead_auditor",
        },
        "expected_output": {
            "verdict": "PASS",
            "min_results": 3,
        },
    },
    {
        "input": {
            "query": "What are the transparency obligations under EU AI Act Article 13?",
            "persona": "legal_counsel",
        },
        "expected_output": {
            "verdict": "PASS",
            "min_results": 3,
        },
    },
    {
        "input": {
            "query": "How does NIST AI RMF define the GOVERN function?",
            "persona": "ml_engineer",
        },
        "expected_output": {
            "verdict": "PASS",
            "min_results": 1,
        },
    },
    {
        "input": {
            "query": "What human oversight requirements apply to high-risk AI under Article 14?",
            "persona": "lead_auditor",
        },
        "expected_output": {
            "verdict": "PASS",
            "min_results": 3,
        },
    },
    {
        "input": {
            "query": "What technical documentation must providers maintain under Article 11?",
            "persona": "legal_counsel",
        },
        "expected_output": {
            "verdict": "PASS",
            "min_results": 3,
        },
    },
    {
        "input": {
            "query": "What are prohibited AI practices under Article 5 of the EU AI Act?",
            "persona": "lead_auditor",
        },
        "expected_output": {
            "verdict": "PASS",
            "min_results": 3,
        },
    },
    {
        "input": {
            "query": "What conformity assessment procedures apply under Article 43?",
            "persona": "legal_counsel",
        },
        "expected_output": {
            "verdict": "PASS",
            "min_results": 1,
        },
    },
    {
        "input": {
            "query": "What are the accuracy and robustness requirements under Article 15?",
            "persona": "lead_auditor",
        },
        "expected_output": {
            "verdict": "PASS",
            "min_results": 1,
        },
    },
    {
        "input": {
            "query": "How does NIST AI RMF MAP function relate to risk identification?",
            "persona": "ml_engineer",
        },
        "expected_output": {
            "verdict": "PASS",
            "min_results": 1,
        },
    },
    {
        "input": {
            "query": "What post-market monitoring obligations exist under Article 72?",
            "persona": "lead_auditor",
        },
        "expected_output": {
            "verdict": "PASS",
            "min_results": 1,
        },
    },
]


# ── Task function (calls LIVE API) ─────────────────────────────────────────────

def task(item: dict) -> dict:
    """Call the live /api/query endpoint and return the response."""
    try:
        resp = requests.post(
            f"{LIVE_API}/api/query",
            json={
                "query": item["input"]["query"],
                "persona": item["input"]["persona"],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {
            "error": str(exc),
            "results": [],
            "claims": [],
            "threshold": 0.88,
            "persona": item["input"].get("persona", "lead_auditor"),
            "query": item["input"].get("query", ""),
        }


# ── Scoring functions ──────────────────────────────────────────────────────────

def _score_result_count(output: dict, expected: dict) -> float:
    """1.0 if result count meets minimum, 0.0 otherwise."""
    results = output.get("results", [])
    min_req = expected.get("min_results", 1)
    return 1.0 if len(results) >= min_req else 0.0


def _score_verdict(output: dict, expected: dict) -> float:
    """1.0 if top result verdict matches expected, 0.0 otherwise."""
    results = output.get("results", [])
    if not results:
        return 0.0
    top_verdict = results[0].get("verdict", "BLOCK")
    expected_verdict = expected.get("verdict", "PASS")
    return 1.0 if top_verdict == expected_verdict else 0.0


def _score_avg_confidence(output: dict, _expected: dict) -> float:
    """Normalized avg_confidence score (0–1)."""
    results = output.get("results", [])
    if not results:
        return 0.0
    avg = sum(r.get("confidence", 0.0) for r in results) / len(results)
    return round(min(1.0, avg), 4)


# ── Opik evaluation runner ─────────────────────────────────────────────────────

def _configure_opik():
    try:
        import opik
        opik.configure(
            api_key=os.getenv("OPIK_API_KEY"),
            workspace=os.getenv("OPIK_WORKSPACE"),
            use_authorization_header=True,
        )
        return True
    except Exception as exc:
        print(f"Opik not available: {exc}")
        return False


def run_evaluation():
    opik_available = _configure_opik()

    if opik_available:
        _run_with_opik()
    else:
        _run_without_opik()


def _run_with_opik():
    try:
        import opik
        from opik.evaluation import evaluate
        from opik.evaluation.metrics import base_metric, score_result

        class ResultCountMetric(base_metric.BaseMetric):
            def score(self, output: dict, expected_output: dict, **kwargs):
                val = _score_result_count(output, expected_output)
                return score_result.ScoreResult(
                    name=self.name, value=val,
                    reason=f"{len(output.get('results', []))} results returned",
                )

        class VerdictAccuracyMetric(base_metric.BaseMetric):
            def score(self, output: dict, expected_output: dict, **kwargs):
                val = _score_verdict(output, expected_output)
                top = output.get("results", [{}])[0].get("verdict", "NONE") if output.get("results") else "NONE"
                return score_result.ScoreResult(
                    name=self.name, value=val,
                    reason=f"top verdict: {top}",
                )

        class ConfidenceMetric(base_metric.BaseMetric):
            def score(self, output: dict, expected_output: dict, **kwargs):
                val = _score_avg_confidence(output, expected_output)
                return score_result.ScoreResult(
                    name=self.name, value=val,
                    reason=f"avg confidence: {val}",
                )

        # Create or reuse dataset
        client = opik.Opik()
        try:
            dataset = client.get_dataset("regulens-benchmarks")
            print("Using existing Opik dataset 'regulens-benchmarks'.")
        except Exception:
            dataset = client.create_dataset(
                name="regulens-benchmarks",
                description="ReguLens EU AI Act / NIST AI RMF benchmark queries",
            )
            dataset.insert(BENCHMARK_ITEMS)
            print(f"Created Opik dataset 'regulens-benchmarks' with {len(BENCHMARK_ITEMS)} items.")

        print(f"\nRunning Opik evaluation against {LIVE_API} ...")
        results = evaluate(
            dataset=dataset,
            task=task,
            scoring_metrics=[
                ResultCountMetric(name="result_count"),
                VerdictAccuracyMetric(name="verdict_accuracy"),
                ConfidenceMetric(name="avg_confidence"),
            ],
            experiment_name="regulens-prompt4-eval",
            task_threads=1,
        )
        print("\nEvaluation complete. Results in Opik dashboard → project 'regulens'.")
        return results

    except Exception as exc:
        print(f"Opik evaluation error: {exc}")
        print("Falling back to offline evaluation...")
        _run_without_opik()


def _run_without_opik():
    print(f"\nRunning offline evaluation against {LIVE_API} ({len(BENCHMARK_ITEMS)} items)...\n")
    scores = {"result_count": [], "verdict_accuracy": [], "avg_confidence": []}

    for i, item in enumerate(BENCHMARK_ITEMS, 1):
        q = item["input"]["query"][:60]
        persona = item["input"]["persona"]
        print(f"[{i:2d}/{len(BENCHMARK_ITEMS)}] {persona} | {q}...")

        output = task(item)

        if "error" in output:
            print(f"       ERROR: {output['error']}")
            scores["result_count"].append(0.0)
            scores["verdict_accuracy"].append(0.0)
            scores["avg_confidence"].append(0.0)
            continue

        rc = _score_result_count(output, item["expected_output"])
        va = _score_verdict(output, item["expected_output"])
        ac = _score_avg_confidence(output, item["expected_output"])
        scores["result_count"].append(rc)
        scores["verdict_accuracy"].append(va)
        scores["avg_confidence"].append(ac)

        top_v = output.get("results", [{}])[0].get("verdict", "NONE") if output.get("results") else "NONE"
        print(f"       results={len(output.get('results',[]))}, verdict={top_v}, confidence={ac}")

    print("\n── Summary ─────────────────────────────────────────")
    for metric, vals in scores.items():
        avg = round(sum(vals) / len(vals), 4) if vals else 0.0
        print(f"  {metric}: {avg}")
    print("────────────────────────────────────────────────────")


if __name__ == "__main__":
    run_evaluation()
