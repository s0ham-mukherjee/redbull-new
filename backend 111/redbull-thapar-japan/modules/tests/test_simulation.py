"""_grounding_block, OasisSwarmSimulator offline paths, MiroFish HTTP bridge."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import requests as real_requests

from engine_api import Evidence, Persona, Scenario
from engine_api.protocols import Simulator
from providers._bootstrap import ProviderError
from providers.simulation import (
    MiroFishServiceSimulator,
    OasisSwarmSimulator,
    _grounding_block,
)


def _ev(content: str = "grounded claim", source: str = "reddit") -> Evidence:
    return Evidence(source=source, url="https://example.com/x", content=content)


# ---------------------------------------------------------------------------
# _grounding_block
# ---------------------------------------------------------------------------


def test_grounding_block_empty():
    assert _grounding_block([]) == "(no external evidence provided)"


def test_grounding_block_five_or_fewer_all_included():
    evs = [_ev(f"claim {i}", source=f"s{i}") for i in range(5)]
    block = _grounding_block(evs)
    lines = block.split("\n")
    assert len(lines) == 5
    for i, line in enumerate(lines):
        assert line == f"- (s{i}) https://example.com/x: claim {i}"


def test_grounding_block_more_than_five_limited_to_five():
    evs = [_ev(f"claim {i}") for i in range(9)]
    lines = _grounding_block(evs).split("\n")
    assert len(lines) == 5
    assert lines[0].endswith("claim 0")
    assert lines[-1].endswith("claim 4")


def test_grounding_block_whitespace_collapsed():
    ev = _ev("para one\n\npara    two\t\tthree")
    line = _grounding_block([ev]).split("\n")[0]
    assert line.endswith("para one para two three")


def test_grounding_block_snippet_capped_at_400_chars():
    ev = _ev("x" * 5000)
    line = _grounding_block([ev]).split("\n")[0]
    snippet = line.rsplit(": ", 1)[1]
    assert len(snippet) == 400


def test_grounding_block_custom_limit():
    evs = [_ev(str(i)) for i in range(3)]
    assert len(_grounding_block(evs, limit=2).split("\n")) == 2


# ---------------------------------------------------------------------------
# OasisSwarmSimulator (offline parts)
# ---------------------------------------------------------------------------


def test_oasis_constructor_offline():
    sim = OasisSwarmSimulator()
    assert sim._steps == 3
    assert sim._platform == "reddit"


@pytest.mark.parametrize("steps,expected", [(0, 1), (-5, 1), (7, 7), (2.9, 2), ("3", 3)])
def test_oasis_steps_clamped(steps, expected):
    assert OasisSwarmSimulator(steps=steps)._steps == expected


def test_oasis_run_without_personas_raises_before_oasis_import(monkeypatch):
    monkeypatch.setitem(sys.modules, "oasis", None)  # import would explode
    sim = OasisSwarmSimulator()
    with pytest.raises(ProviderError, match="at least one persona"):
        sim.run(Scenario(id="sc", ip_id="i", prompt="p"), personas=[])
    # the error came from the persona check, not the (broken) oasis import


def test_persona_description_contents():
    sim = OasisSwarmSimulator()
    persona = Persona(id="p1", tier="tier_2", location=None,
                      languages=("hi", "en"), preferred_formats=("dub", "sub"),
                      genres=("shonen", "slice of life"),
                      disposable_income_inr=8123.6)
    desc = sim._persona_description(persona, [_ev("evidence line")])
    assert "tier_2" in desc
    assert "India" in desc  # location fallback
    assert "hi, en" in desc
    assert "dub, sub" in desc
    assert "shonen, slice of life" in desc
    assert "INR 8124" in desc  # :.0f rounding
    assert "- (reddit) https://example.com/x: evidence line" in desc


def test_persona_description_location_set():
    sim = OasisSwarmSimulator()
    desc = sim._persona_description(
        Persona(id="p", location="Patna", languages=("hi",)), [])
    assert "Patna" in desc
    assert "(no external evidence provided)" in desc


def test_oasis_satisfies_protocol():
    assert isinstance(OasisSwarmSimulator(), Simulator)


def test_oasis_via_registry(reg):
    sim = reg.create("simulator", "oasis_swarm")
    assert isinstance(sim, Simulator)


# ---------------------------------------------------------------------------
# MiroFishServiceSimulator with a fake HTTP layer
# ---------------------------------------------------------------------------


class FakeResp:
    def __init__(self, payload=None, ok=True, status_code=200, content=b"x"):
        self._payload = payload
        self.ok = ok
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise real_requests.exceptions.HTTPError(f"{self.status_code}")

    def json(self):
        return self._payload


def _fake_http(post=None, get=None):
    return SimpleNamespace(
        post=post or (lambda *a, **k: FakeResp({})),
        get=get or (lambda *a, **k: FakeResp({})),
        exceptions=real_requests.exceptions,
    )


def test_mirofish_default_base_url():
    sim = MiroFishServiceSimulator()
    assert sim._base == "http://localhost:5001"


def test_mirofish_trailing_slash_stripped():
    assert MiroFishServiceSimulator(base_url="http://mf:5001/")._base == "http://mf:5001"
    assert MiroFishServiceSimulator(base_url="http://mf:5001///")._base == "http://mf:5001"


def test_mirofish_env_override(monkeypatch):
    monkeypatch.setenv("MIROFISH_URL", "http://env-host:6001/")
    assert MiroFishServiceSimulator()._base == "http://env-host:6001"
    # explicit base_url beats env
    assert MiroFishServiceSimulator(base_url="http://explicit:1/")._base == \
        "http://explicit:1"


def _scenario(**attrs):
    return Scenario(id="sc1", ip_id="i", prompt="p", attributes=attrs)


def test_mirofish_run_without_project_id(monkeypatch):
    monkeypatch.setattr(MiroFishServiceSimulator, "_post",
                        lambda self, path, payload: (_ for _ in ()).throw(
                            AssertionError("must not POST")))
    sim = MiroFishServiceSimulator()
    with pytest.raises(ProviderError, match="project_id"):
        sim.run(_scenario(), [Persona(id="p")])


def test_mirofish_post_connection_error(monkeypatch):
    def raising_post(url, json=None, timeout=None):
        raise real_requests.exceptions.ConnectionError("refused")

    sim = MiroFishServiceSimulator()
    monkeypatch.setattr(sim, "_http", _fake_http(post=raising_post))
    with pytest.raises(ProviderError, match="cannot reach MiroFish"):
        sim._post("/api/simulation/create", {})


def test_mirofish_run_success(monkeypatch):
    sim = MiroFishServiceSimulator()
    posted = []

    def post(url, json=None, timeout=None):
        posted.append((url, json))
        return FakeResp({"data": {"simulation_id": "s1"}})

    monkeypatch.setattr(sim, "_http", _fake_http(post=post))
    report = sim.run(_scenario(project_id="proj-9", enable_twitter=False),
                     [Persona(id="p1"), Persona(id="p2")],
                     evidence=[_ev()], seed=11)
    assert report.scenario_id == "sc1"
    assert report.seed == 11
    assert report.turns == ()
    assert report.metadata["engine"] == "mirofish_service"
    assert report.metadata["simulation_id"] == "s1"
    assert report.metadata["project_id"] == "proj-9"
    assert report.metadata["persona_count"] == 2
    assert report.metadata["evidence_count"] == 1
    assert report.started_at is not None
    path, payload = posted[0]
    assert path.endswith("/api/simulation/create")
    assert payload["project_id"] == "proj-9"
    assert payload["enable_twitter"] is False
    assert payload["enable_reddit"] is True
    assert "graph_id" not in payload  # absent when not provided


def test_mirofish_run_includes_graph_id_when_present(monkeypatch):
    sim = MiroFishServiceSimulator()
    posted = []

    def post(url, json=None, timeout=None):
        posted.append(json)
        return FakeResp({"data": {"simulation_id": "s2"}})

    monkeypatch.setattr(sim, "_http", _fake_http(post=post))
    sim.run(_scenario(project_id="p", graph_id="g1"), [])
    assert posted[0]["graph_id"] == "g1"


def test_mirofish_run_top_level_simulation_id(monkeypatch):
    sim = MiroFishServiceSimulator()
    monkeypatch.setattr(sim, "_http",
                        _fake_http(post=lambda url, json=None, timeout=None:
                                   FakeResp({"simulation_id": "top-level"})))
    report = sim.run(_scenario(project_id="p"), [])
    assert report.metadata["simulation_id"] == "top-level"


def test_mirofish_run_unexpected_response(monkeypatch):
    sim = MiroFishServiceSimulator()
    monkeypatch.setattr(sim, "_http",
                        _fake_http(post=lambda url, json=None, timeout=None:
                                   FakeResp({"data": {}})))
    with pytest.raises(ProviderError, match="unexpected MiroFish create response"):
        sim.run(_scenario(project_id="p"), [])


def test_mirofish_health_ok(monkeypatch):
    sim = MiroFishServiceSimulator()
    monkeypatch.setattr(sim, "_http",
                        _fake_http(get=lambda url, **k: FakeResp({}, ok=True,
                                                                 status_code=200)))
    assert sim.health() == {"reachable": True, "status_code": 200}


def test_mirofish_health_error(monkeypatch):
    sim = MiroFishServiceSimulator()

    def raising_get(url, **k):
        raise real_requests.exceptions.ConnectionError("no route")

    monkeypatch.setattr(sim, "_http", _fake_http(get=raising_get))
    out = sim.health()
    assert out["reachable"] is False
    assert "no route" in out["error"]


def test_mirofish_satisfies_protocol():
    assert isinstance(MiroFishServiceSimulator(), Simulator)


def test_mirofish_via_registry(reg):
    sim = reg.create("simulator", "mirofish_service")
    assert isinstance(sim, Simulator)
