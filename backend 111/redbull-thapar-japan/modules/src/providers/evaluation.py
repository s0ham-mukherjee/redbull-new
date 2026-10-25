"""Agent evaluation (upstream clone: confident-ai/deepeval, Apache-2.0).

Exposed capability: ``evaluator`` / ``factual_consistency`` - faithfulness of
simulation output against grounded evidence (Features 46/78).
"""

from __future__ import annotations

from typing import Any, Sequence

from engine_api import EvaluationResult, Evidence, SimulationReport, provider

from ._bootstrap import ProviderError


class FactualConsistencyEvaluator:
    """Evaluator wrapping deepeval's FaithfulnessMetric.

    ``evaluate`` scores each simulation turn's claims against the retrieved
    evidence texts; a deterministic citation check runs first so the engine
    gets a usable score even without an LLM judge configured.
    """

    def __init__(self, threshold: float = 0.7, use_llm_judge: bool = False,
                 model: str | None = None) -> None:
        self._threshold = threshold
        self._use_llm_judge = use_llm_judge
        self._model = model

    # -- deterministic pre-check -----------------------------------------
    @staticmethod
    def _citation_coverage(report: SimulationReport, evidence: Sequence[Evidence]) -> float:
        if not report.turns:
            return 0.0
        grounded = sum(1 for turn in report.turns if turn.cited_evidence)
        return grounded / len(report.turns)

    def evaluate(
        self,
        report: SimulationReport,
        evidence: Sequence[Evidence] = (),
    ) -> EvaluationResult:
        if not report.turns:
            return EvaluationResult(
                passed=False, score=0.0,
                details={"reason": "simulation produced no turns"},
            )
        coverage = self._citation_coverage(report, evidence)
        details: dict[str, Any] = {"citation_coverage": coverage, "turns": len(report.turns)}

        if not self._use_llm_judge:
            # Offline mode: turns must cite evidence for the run to pass.
            passed = coverage >= self._threshold
            details["mode"] = "deterministic"
            details["threshold"] = self._threshold
            return EvaluationResult(passed=passed, score=coverage, details=details)

        # LLM-judged faithfulness via deepeval.
        try:
            from deepeval import evaluate as deepeval_evaluate  # lazy upstream import
            from deepeval.metrics import FaithfulnessMetric
            from deepeval.test_case import LLMTestCase
        except Exception as exc:
            raise ProviderError(f"deepeval unavailable: {exc}") from exc

        contexts = [ev.content for ev in evidence] or ["(no evidence)"]
        actual_output = " ".join(turn.text for turn in report.turns)
        test_case = LLMTestCase(
            input=report.scenario_id,
            actual_output=actual_output,
            retrieval_context=contexts,
        )
        metric = FaithfulnessMetric(threshold=self._threshold, model=self._model)
        try:
            result = deepeval_evaluate(test_case, [metric])
        except Exception as exc:
            raise ProviderError(f"deepeval evaluation failed: {exc}") from exc

        score = float(metric.score) if metric.score is not None else 0.0
        details.update({
            "mode": "llm_judge",
            "reason": getattr(metric, "reason", None),
            "overall_pass": bool(getattr(result, "overall_pass", score >= self._threshold)),
        })
        return EvaluationResult(passed=score >= self._threshold, score=score, details=details)


@provider("evaluator", "factual_consistency")
def _factory(**config: Any) -> FactualConsistencyEvaluator:
    return FactualConsistencyEvaluator(**config)


__all__ = ["FactualConsistencyEvaluator"]
