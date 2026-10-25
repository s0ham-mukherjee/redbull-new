"""Presentation & API glue (upstream clones: fastapi/fastapi MIT, streamlit/streamlit Apache-2.0).

Exposed capabilities:
- ``app`` / ``decision_api`` - FastAPI app exposing health, capability
  listing and a generic directive endpoint for the engine (Feature "glue").
- ``ui`` / ``decision_dashboard`` - Streamlit rendering helpers for scores,
  evidence tables and scenario controls (Features 71/72/80).
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from engine_api import Directive, Evidence, provider

from ._bootstrap import ProviderError


def _build_request_model() -> Any:
    """Build the /research body model at module resolution time.

    Defined via a factory because ``from __future__ import annotations``
    stringifies annotations; a function-local class would remain an
    unresolvable ForwardRef when FastAPI inspects the route signature.
    """
    try:
        from pydantic import BaseModel
    except Exception as exc:  # pragma: no cover
        raise ProviderError(f"pydantic unavailable: {exc}") from exc

    class ResearchRequest(BaseModel):
        kind: str = "source"
        provider: str
        text: str = ""
        region: str | None = None
        limit: int = 10
        extra: dict[str, Any] = {}

    return ResearchRequest


def create_decision_api(
    engine_fetch: Callable[[str, str, dict], Sequence[Evidence]] | None = None,
    title: str = "SakuraScore Engine API",
) -> Any:
    """Build a FastAPI app wired to the provider registry.

    ``engine_fetch(kind, name, query_dict) -> Sequence[Evidence]`` lets the
    pre-existing engine inject its own fetching logic; without it the app
    still serves /health and /capabilities.
    """
    try:
        from fastapi import FastAPI, HTTPException  # lazy upstream import
    except Exception as exc:
        raise ProviderError(f"fastapi unavailable: {exc}") from exc

    from engine_api import Query, available

    app = FastAPI(title=title, version="1.0")
    model_cls = _build_request_model()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/capabilities")
    def capabilities() -> dict[str, list[str]]:
        return available()

    def research(req: Any) -> dict[str, Any]:
        if engine_fetch is None:
            raise HTTPException(status_code=503, detail="engine did not attach a fetch handler")
        query = Query(text=req.text, region=req.region, limit=req.limit, extra=req.extra)
        try:
            results = engine_fetch(req.kind, req.provider, query)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "count": len(results),
            "evidence": [
                {
                    "source": e.source,
                    "url": e.url,
                    "title": e.title,
                    "content_hash": e.content_hash,
                    "retrieved_at": e.retrieved_at.isoformat(),
                }
                for e in results
            ],
        }

    # Bind the concrete model to the route signature (stringified annotation
    # would otherwise remain a ForwardRef FastAPI resolves against globals).
    research.__annotations__["req"] = model_cls
    app.post("/research")(research)

    return app


class DecisionDashboard:
    """UI helpers: pure data -> renderable dicts for a Streamlit front-end.

    Kept import-light so the engine can ship without Streamlit installed;
    ``render_*`` methods import streamlit lazily when called.
    """

    def __init__(self, page_title: str = "SakuraScore India") -> None:
        self._page_title = page_title

    def directive_rows(self, directives: Sequence[Directive]) -> list[dict[str, Any]]:
        return [
            {
                "ip_id": d.ip_id,
                "action": d.action.value,
                "opportunity": round(d.opportunity_score, 3),
                "forecast": (
                    f"{d.forecast.interval.point:.0f} "
                    f"[{d.forecast.interval.lower:.0f}, {d.forecast.interval.upper:.0f}]"
                    if d.forecast and d.forecast.ready
                    else "n/a (insufficient data)"
                ),
                "rationale": d.rationale,
            }
            for d in directives
        ]

    def render_directives(self, directives: Sequence[Directive]) -> None:
        try:
            import streamlit as st  # lazy upstream import
        except Exception as exc:
            raise ProviderError(f"streamlit unavailable: {exc}") from exc
        st.title(self._page_title)
        rows = self.directive_rows(directives)
        if not rows:
            st.info("No directives yet - run an assessment first.")
            return
        st.dataframe(rows, use_container_width=True)
        for row in rows:
            color = {"pilot": "green", "investigate": "blue",
                     "wait": "orange", "abstain": "red"}.get(row["action"], "gray")
            st.markdown(f"**:{color}: {row['action'].upper()}** - `{row['ip_id']}`")

    def render_evidence(self, evidence: Sequence[Evidence]) -> None:
        try:
            import streamlit as st
        except Exception as exc:
            raise ProviderError(f"streamlit unavailable: {exc}") from exc
        st.subheader(f"Evidence ({len(evidence)})")
        st.table([
            {"source": e.source, "title": e.title or "", "url": e.url,
             "hash": e.content_hash[:12]}
            for e in evidence
        ])


@provider("app", "decision_api")
def _app_factory(**config: Any) -> Any:
    engine_fetch = config.pop("engine_fetch", None)
    return create_decision_api(engine_fetch=engine_fetch, **config)


@provider("ui", "decision_dashboard")
def _ui_factory(**config: Any) -> DecisionDashboard:
    return DecisionDashboard(**config)


__all__ = ["create_decision_api", "DecisionDashboard"]
