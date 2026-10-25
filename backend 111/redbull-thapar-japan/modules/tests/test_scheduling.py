"""PrefectScheduler with a stubbed prefect.flow (real clone import is broken
offline: `from prefect import flow` raises ImportError in this environment)."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from engine_api.protocols import Scheduler
from providers._bootstrap import ProviderError
from providers.scheduling import PrefectScheduler


@pytest.fixture()
def prefect_stub(monkeypatch):
    """Stub prefect.flow(fn, name=...) -> wrapper calling fn directly."""
    created = []

    def flow(fn, name=None):
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        created.append(name)
        return wrapper

    stub = SimpleNamespace(flow=flow)
    monkeypatch.setitem(sys.modules, "prefect", stub)
    return stub, created


def test_submit_non_callable_rejected_without_prefect():
    with pytest.raises(ProviderError, match="must be callable"):
        PrefectScheduler().submit("j", "not-callable")


def test_submit_with_broken_prefect_import_raises_actionably(monkeypatch):
    # sys.modules None -> ImportError -> ProviderError (current mapping)
    monkeypatch.setitem(sys.modules, "prefect", None)
    with pytest.raises(ProviderError, match="prefect unavailable"):
        PrefectScheduler().submit("j", lambda: 1)


def test_submit_run_round_trip(prefect_stub):
    _, created = prefect_stub
    sched = PrefectScheduler()
    sched.submit("double", lambda x: x * 2, cron="0 * * * *")
    assert created == ["double"]
    assert sched.run("double", 21) == 42


def test_run_unknown_job_lists_registered(prefect_stub):
    sched = PrefectScheduler()
    with pytest.raises(ProviderError, match=r"unknown job: 'nope' \(registered: \[\]\)"):
        sched.run("nope")
    sched.submit("a", lambda: 1)
    sched.submit("b", lambda: 2)
    with pytest.raises(ProviderError) as exc:
        sched.run("zzz")
    assert "'a'" in str(exc.value) and "'b'" in str(exc.value)


def test_run_returns_function_result(prefect_stub):
    sched = PrefectScheduler()
    sched.submit("compute", lambda a, b=0: a + b)
    assert sched.run("compute", 2, b=3) == 5


def test_job_failure_wrapped_as_provider_error(prefect_stub):
    sched = PrefectScheduler()
    sched.submit("bad", lambda: (_ for _ in ()).throw(ValueError("kaboom")))
    with pytest.raises(ProviderError, match="failed"):
        sched.run("bad")


def test_job_raising_value_error_directly(prefect_stub):
    sched = PrefectScheduler()

    def boom():
        raise ValueError("direct raise")

    sched.submit("boom", boom)
    with pytest.raises(ProviderError, match="kaboom|boom"):
        sched.run("boom")


def test_schedules_cron_mapping(prefect_stub):
    sched = PrefectScheduler()
    sched.submit("no_cron", lambda: 1)
    sched.submit("hourly", lambda: 2, cron="0 * * * *")
    sched.submit("daily", lambda: 3, cron="0 9 * * 1")
    assert sched.schedules() == {"no_cron": None, "hourly": "0 * * * *",
                                 "daily": "0 9 * * 1"}


def test_jobs_sorted(prefect_stub):
    sched = PrefectScheduler()
    sched.submit("c", lambda: 1)
    sched.submit("a", lambda: 2)
    sched.submit("b", lambda: 3)
    assert sched.jobs() == ["a", "b", "c"]


def test_same_name_resubmit_replaces(prefect_stub):
    sched = PrefectScheduler()
    sched.submit("j", lambda: "first")
    sched.submit("j", lambda: "second")
    assert sched.jobs() == ["j"]
    assert sched.run("j") == "second"


def test_submit_returns_name(prefect_stub):
    sched = PrefectScheduler()
    assert sched.submit("named", lambda: 0) == "named"


def test_scheduler_satisfies_protocol():
    assert isinstance(PrefectScheduler(), Scheduler)


def test_scheduler_via_registry(reg, prefect_stub):
    sched = reg.create("scheduler", "prefect")
    assert isinstance(sched, Scheduler)
    sched.submit("zzz_job", lambda: 7)
    assert sched.run("zzz_job") == 7
