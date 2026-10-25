"""Multi-agent audience simulation.

Upstream clones: camel-ai/oasis (Apache-2.0), 666ghj/MiroFish (AGPL-3.0).

Exposed capabilities:
- ``simulator`` / ``oasis_swarm`` - in-process OASIS social simulation
  seeded with personas + grounded evidence (Features 21-23, 44, 50).
- ``simulator`` / ``mirofish_service`` - HTTP bridge to a *running* MiroFish
  backend (Flask API, default :5001).

Licensing note: MiroFish is AGPL-3.0, so no MiroFish code is imported or
vendored here - the adapter only speaks to it over HTTP as an independent
service, keeping this package's license untouched.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Sequence

from engine_api import (
    AgentTurn,
    Evidence,
    Persona,
    Scenario,
    SimulationReport,
    provider,
)

from ._bootstrap import ProviderError, ensure_paths


def _grounding_block(evidence: Sequence[Evidence], limit: int = 5) -> str:
    """Evidence snippets injected into agent prompts to prevent hallucination (RAS)."""
    lines = []
    for ev in list(evidence)[:limit]:
        snippet = " ".join(ev.content.split())[:400]
        lines.append(f"- ({ev.source}) {ev.url}: {snippet}")
    return "\n".join(lines) if lines else "(no external evidence provided)"


class OasisSwarmSimulator:
    """Simulator backed by OASIS (Apache-2.0) with evidence-grounded personas.

    Requires ``camel-ai`` and an LLM API key (OPENAI_API_KEY etc.) at run time.
    """

    def __init__(
        self,
        platform: str = "reddit",
        steps: int = 3,
        model_platform: str = "openai",
        model_type: str = "gpt-4o-mini",
    ) -> None:
        ensure_paths("oasis")
        self._platform = platform
        self._steps = max(1, int(steps))
        self._model_platform = model_platform
        self._model_type = model_type

    # -- helpers -----------------------------------------------------------
    def _model(self) -> Any:
        from camel.models import ModelFactory  # lazy upstream import
        from camel.types import ModelPlatformType, ModelType

        platform = getattr(ModelPlatformType, self._model_platform.upper(), None)
        mtype = getattr(ModelType, self._model_type.upper(), None)
        if platform is None or mtype is None:
            raise ProviderError(
                f"unknown model platform/type: {self._model_platform}/{self._model_type}"
            )
        return ModelFactory.create(model_platform=platform, model_type=mtype)

    def _persona_description(self, persona: Persona, evidence: Sequence[Evidence]) -> str:
        # Economic constraints are part of the profile so agents cannot claim
        # purchase intent beyond their disposable income (anti-hallucination).
        return (
            f"Audience member in {persona.tier} ({persona.location or 'India'}). "
            f"Languages: {', '.join(persona.languages)}. "
            f"Prefers: {', '.join(persona.preferred_formats)}; genres: {', '.join(persona.genres)}. "
            f"Monthly disposable income: INR {persona.disposable_income_inr:.0f}. "
            f"Context from verified market evidence:\n{_grounding_block(evidence)}"
        )

    # -- Simulator ---------------------------------------------------------
    def run(
        self,
        scenario: Scenario,
        personas: Sequence[Persona],
        evidence: Sequence[Evidence] = (),
        seed: int = 0,
    ) -> SimulationReport:
        if not personas:
            raise ProviderError("oasis_swarm requires at least one persona")

        import oasis  # lazy upstream import
        from oasis import AgentGraph, ActionType, LLMAction, ManualAction, SocialAgent, UserInfo

        model = self._model()
        available_actions = [
            ActionType.CREATE_POST,
            ActionType.CREATE_COMMENT,
            ActionType.LIKE_POST,
        ]
        agent_graph = AgentGraph()
        agents = []
        for idx, persona in enumerate(personas):
            agent = SocialAgent(
                agent_id=idx,
                user_info=UserInfo(
                    user_name=persona.id,
                    name=persona.id,
                    description=self._persona_description(persona, evidence),
                    profile=None,
                    recsys_type=self._platform,
                ),
                agent_graph=agent_graph,
                model=model,
                available_actions=available_actions,
            )
            agent_graph.add_agent(agent)
            agents.append(agent)

        tmpdir = tempfile.mkdtemp(prefix="sakurascore_oasis_")
        db_path = os.path.join(tmpdir, f"sim_{scenario.id}_{seed}.db")
        os.environ["OASIS_DB_PATH"] = db_path

        env = oasis.make(
            agent_graph=agent_graph,
            platform=oasis.DefaultPlatformType.REDDIT,
            database_path=db_path,
        )

        price_note = ", ".join(
            f"{k}=INR {v:.0f}" for k, v in scenario.price_points_inr.items()
        ) or "not specified"
        prompt = (
            f"Market test discussion. Scenario: {scenario.prompt} "
            f"(price points: {price_note}). Debate whether audiences in India "
            f"would watch, pay, or skip - cite only the provided evidence."
        )

        started = datetime.now(timezone.utc)
        turns: list[AgentTurn] = []

        async def _loop() -> None:
            await env.reset()
            # Seed the debate with the scenario post from agent 0.
            seed_action = {
                agents[0]: [
                    ManualAction(action_type=ActionType.CREATE_POST,
                                 action_args={"content": prompt})
                ]
            }
            await env.step(seed_action)
            for step in range(self._steps):
                llm_actions = {agent: LLMAction() for agent in agents}
                await env.step(llm_actions)
                turns.append(
                    AgentTurn(
                        agent_id="swarm",
                        stance="debate",
                        text=f"completed simulation step {step + 1}",
                        step=step,
                    )
                )
            await env.close()

        try:
            asyncio.run(_loop())
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"oasis simulation failed: {exc}") from exc

        return SimulationReport(
            scenario_id=scenario.id,
            seed=seed,
            turns=tuple(turns),
            # Aggregation happens downstream (calibration layer), not in-sim.
            demand_distribution={},
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            metadata={
                "engine": "oasis",
                "platform": self._platform,
                "agents": len(agents),
                "steps": self._steps,
                "db_path": db_path,
                "model": f"{self._model_platform}/{self._model_type}",
            },
        )


class MiroFishServiceSimulator:
    """Simulator bridging a running MiroFish backend over HTTP (no code copied)."""

    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        self._base = (base_url or os.environ.get("MIROFISH_URL") or "http://localhost:5001").rstrip("/")
        self._timeout = timeout
        try:
            import requests
        except ImportError as exc:  # pragma: no cover
            raise ProviderError("requests is required for MiroFishServiceSimulator") from exc
        self._http = requests

    def _post(self, path: str, payload: Any) -> Any:
        try:
            resp = self._http.post(f"{self._base}{path}", json=payload, timeout=self._timeout)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except self._http.exceptions.ConnectionError as exc:
            raise ProviderError(
                f"cannot reach MiroFish at {self._base} "
                f"(start the backend or set MIROFISH_URL): {exc}"
            ) from exc
        except Exception as exc:
            raise ProviderError(f"MiroFish request {path} failed: {exc}") from exc

    def health(self) -> dict[str, Any]:
        try:
            resp = self._http.get(f"{self._base}/api/simulation/list", timeout=self._timeout)
            return {"reachable": resp.ok, "status_code": resp.status_code}
        except Exception as exc:
            return {"reachable": False, "error": str(exc)}

    def run(
        self,
        scenario: Scenario,
        personas: Sequence[Persona],
        evidence: Sequence[Evidence] = (),
        seed: int = 0,
    ) -> SimulationReport:
        project_id = str(scenario.attributes.get("project_id") or "")
        if not project_id:
            raise ProviderError(
                "mirofish_service needs scenario.attributes['project_id'] "
                "(create the project in MiroFish first)"
            )
        graph_id = scenario.attributes.get("graph_id")
        created = self._post(
            "/api/simulation/create",
            {
                "project_id": project_id,
                **({"graph_id": graph_id} if graph_id else {}),
                "enable_twitter": bool(scenario.attributes.get("enable_twitter", True)),
                "enable_reddit": bool(scenario.attributes.get("enable_reddit", True)),
            },
        )
        payload = created.get("data") or created
        sim_id = payload.get("simulation_id")
        if not sim_id:
            raise ProviderError(f"unexpected MiroFish create response: {created}")
        # Hand off to MiroFish's own prepare/report endpoints; final
        # aggregation and evidence are returned by the engine downstream.
        return SimulationReport(
            scenario_id=scenario.id,
            seed=seed,
            turns=(),
            demand_distribution={},
            started_at=datetime.now(timezone.utc),
            metadata={
                "engine": "mirofish_service",
                "simulation_id": sim_id,
                "project_id": project_id,
                "persona_count": len(personas),
                "evidence_count": len(evidence),
                "created": payload,
            },
        )


@provider("simulator", "oasis_swarm")
def _oasis_factory(**config: Any) -> OasisSwarmSimulator:
    return OasisSwarmSimulator(**config)


@provider("simulator", "mirofish_service")
def _mirofish_factory(**config: Any) -> MiroFishServiceSimulator:
    return MiroFishServiceSimulator(**config)


__all__ = ["OasisSwarmSimulator", "MiroFishServiceSimulator", "json"]
