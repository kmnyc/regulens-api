"""Custom Opik evaluation metrics for ReguLens compliance pipeline."""

from __future__ import annotations

try:
    from opik.evaluation.metrics import base_metric, score_result

    class ClaimAccuracyMetric(base_metric.BaseMetric):
        """Fraction of claims verified as PASS out of total claims."""

        def __init__(self, name: str = "claim_accuracy"):
            super().__init__(name=name)

        def score(self, output: dict, **kwargs) -> score_result.ScoreResult:
            claims = output.get("claims", [])
            if not claims:
                return score_result.ScoreResult(
                    name=self.name, value=0.0, reason="No claims to evaluate"
                )
            passed = sum(1 for c in claims if c.get("verdict") == "PASS")
            ratio = round(passed / len(claims), 4)
            return score_result.ScoreResult(
                name=self.name,
                value=ratio,
                reason=f"{passed}/{len(claims)} claims verified as PASS",
            )

    class ThresholdComplianceMetric(base_metric.BaseMetric):
        """1.0 if avg_confidence meets persona threshold, else ratio of avg/threshold."""

        def __init__(self, name: str = "threshold_compliance"):
            super().__init__(name=name)

        def score(self, output: dict, **kwargs) -> score_result.ScoreResult:
            avg_conf = output.get("avg_confidence", 0.0)
            threshold = output.get("threshold", 0.96)
            if threshold == 0:
                return score_result.ScoreResult(
                    name=self.name, value=0.0, reason="Threshold is zero"
                )
            ratio = min(1.0, round(avg_conf / threshold, 4))
            meets = avg_conf >= threshold
            return score_result.ScoreResult(
                name=self.name,
                value=ratio,
                reason=(
                    f"avg_confidence {avg_conf} {'meets' if meets else 'below'} "
                    f"threshold {threshold}"
                ),
            )

except ImportError:
    # Opik not installed — metrics are no-ops
    class ClaimAccuracyMetric:  # type: ignore[no-redef]
        def __init__(self, name: str = "claim_accuracy"):
            self.name = name

        def score(self, output: dict, **kwargs):
            return None

    class ThresholdComplianceMetric:  # type: ignore[no-redef]
        def __init__(self, name: str = "threshold_compliance"):
            self.name = name

        def score(self, output: dict, **kwargs):
            return None
