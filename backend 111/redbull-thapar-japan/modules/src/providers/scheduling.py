"""Workflow orchestration for continuous research (upstream clone: prefecthq/prefect, Apache-2.0).

Exposed capability: ``scheduler`` / ``prefect`` - submit named jobs (with
optional cron) and run them through Prefect's flow engine (Features 61/64/69).
"""

from __future__ import annotations

from typing import Any, Callable

from engine_api import provider

from ._bootstrap import ProviderError, ensure_paths


class PrefectScheduler:
    """Scheduler wrapping Prefect flows.

    Jobs are registered as Prefect flows; ``submit`` records the schedule and
    ``run`` executes a job now (returning the flow result). Cron strings are
    stored for the engine's external cron/daemon to trigger ``run``.
    """

    def __init__(self, work_pool: str | None = None) -> None:
        ensure_paths("prefect")
        self._work_pool = work_pool
        self._jobs: dict[str, dict[str, Any]] = {}

    def submit(self, name: str, fn: Callable[..., Any], cron: str | None = None) -> str:
        if not callable(fn):
            raise ProviderError(f"job {name!r} must be callable")
        try:
            from prefect import flow  # lazy upstream import
        except Exception as exc:
            raise ProviderError(f"prefect unavailable: {exc}") from exc
        wrapped = flow(fn, name=name)
        self._jobs[name] = {"flow": wrapped, "cron": cron, "fn": fn}
        return name

    def run(self, name: str, *args: Any, **kwargs: Any) -> Any:
        job = self._jobs.get(name)
        if job is None:
            raise ProviderError(f"unknown job: {name!r} (registered: {sorted(self._jobs)})")
        try:
            return job["flow"](*args, **kwargs)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"job {name!r} failed: {exc}") from exc

    def schedules(self) -> dict[str, str | None]:
        """Cron expressions the external daemon should trigger on."""
        return {name: job["cron"] for name, job in self._jobs.items()}

    def jobs(self) -> list[str]:
        return sorted(self._jobs)


@provider("scheduler", "prefect")
def _factory(**config: Any) -> PrefectScheduler:
    return PrefectScheduler(**config)


__all__ = ["PrefectScheduler"]
