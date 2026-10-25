"""FactualConsistencyEvaluator: deterministic mode + LLM-judge error path."""

from __future__ import annotations

import sys

import pytest

from engine_api import AgentTurn, Evidence, SimulationReport
from engine_api.protocols import Evaluator
from providers._bootstrap import ProviderError
from providers.evaluation import FactualConsistencyEvaluator


def _report(*cited) -> SimulationReport:
    turns = tuple(
        AgentTurn(agent_id=f"a{i}", stance="pro" if i % 2 == 0 else "con",
                  text=f"claim {i}", cited_evidence=cited[i] if i < len(cited) else ())
        for i in range(max(len(cited), 1))
    )
    return SimulationReport(scenario_id="sc", seed=0, turns=turns)


EV = [Evidence(source="t", url="u", content="c")]


def test_no_turns_fails_with_reason():
    ev = FactualConsistencyEvaluator()
    res = ev.evaluate(SimulationReport(scenario_id="sc", seed=0, turns=()), EV)
    assert res.passed is False
    assert res.score == 0.0
    assert "reason" in res.details
    assert res.details["reason"] == "simulation produced no turns"


def test_zero_percent_coverage_fails():
    ev = FactualConsistencyEvaluator(threshold=0.5)
    res = ev.evaluate(_report((), ()), EV)
    assert res.passed is False
    assert res.score == 0.0
    assert res.details["citation_coverage"] == 0.0


def test_fifty_percent_coverage():
    ev = FactualConsistencyEvaluator(threshold=0.5)
    res = ev.evaluate(_report(("h1",), ()), EV)
    assert res.details["citation_coverage"] == 0.5
    assert res.passed is True
    assert res.score == 0.5


def test_hundred_percent_coverage():
    ev = FactualConsistencyEvaluator(threshold=0.7)
    res = ev.evaluate(_report(("h1",), ("h2",)), EV)
    assert res.details["citation_coverage"] == 1.0
    assert res.passed is True
    assert res.score == 1.0


def test_threshold_boundary_exact_equality_passes():
    # coverage exactly == threshold passes (>=)
    ev = FactualConsistencyEvaluator(threshold=0.5)
    res = ev.evaluate(_report(("h",), ()), EV)
    assert res.score == 0.5 and res.passed is True
    # 0.7 > 2/3 -> a 2-of-3 report fails against threshold 0.7
    ev71 = FactualConsistencyEvaluator(threshold=0.7)
    res71 = ev71.evaluate(_report(("h",), ("h",), ()), EV)
    assert res71.details["citation_coverage"] == pytest.approx(2 / 3)
    assert res71.passed is False
    # threshold 0.66 <= 2/3 passes
    ev66 = FactualConsistencyEvaluator(threshold=0.66)
    assert ev66.evaluate(_report(("h",), ("h",), ()), EV).passed is True


def test_score_equals_coverage():
    ev = FactualConsistencyEvaluator(threshold=0.0)
    res = ev.evaluate(_report(("h",), (), ("h",)), EV)
    assert res.score == res.details["citation_coverage"] == pytest.approx(2 / 3)


def test_turns_count_echoed_in_details():
    ev = FactualConsistencyEvaluator()
    res = ev.evaluate(_report(("h",), ("h",), ("h",), ()), EV)
    assert res.details["turns"] == 4


def test_details_mode_and_threshold_recorded():
    ev = FactualConsistencyEvaluator(threshold=0.9)
    res = ev.evaluate(_report(("h",)), EV)
    assert res.details["mode"] == "deterministic"
    assert res.details["threshold"] == 0.9


def test_evidence_irrelevant_in_deterministic_mode():
    ev = FactualConsistencyEvaluator(threshold=0.5)
    rep = _report(("h",), ())
    assert ev.evaluate(rep, [Evidence(source="a", url="u", content="x")] * 10) == \
           ev.evaluate(rep, [])


def test_threshold_zero_passes_even_without_citations():
    # 0.0 >= 0.0 -> passes (current deterministic rule)
    ev = FactualConsistencyEvaluator(threshold=0.0)
    res = ev.evaluate(_report((), ()), EV)
    assert res.passed is True and res.score == 0.0


def test_cited_evidence_truthiness_semantics():
    # any non-empty *tuple* counts as grounded, even ("",); only () is ungrounded
    ev = FactualConsistencyEvaluator(threshold=1.0)
    res = ev.evaluate(_report(("",), ("x",)), EV)
    assert res.details["citation_coverage"] == 1.0
    res2 = ev.evaluate(_report((), ("x",)), EV)
    assert res2.details["citation_coverage"] == 0.5


def test_llm_judge_path_raises_when_deepeval_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "deepeval", None)  # import -> ImportError
    ev = FactualConsistencyEvaluator(use_llm_judge=True)
    with pytest.raises(ProviderError, match="deepeval unavailable"):
        ev.evaluate(_report(("h",)), EV)


def test_evaluator_satisfies_protocol():
    assert isinstance(FactualConsistencyEvaluator(), Evaluator)


def test_evaluator_via_registry(reg):
    ev = reg.create("evaluator", "factual_consistency", threshold=0.5)
    assert isinstance(ev, Evaluator)
    res = ev.evaluate(_report(("h",)), EV)
    assert res.passed is True
