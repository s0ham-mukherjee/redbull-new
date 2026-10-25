"""Deep registry tests beyond test_engine_api.py.

Uses throwaway names prefixed ``zzz_`` under kinds that no other test (and in
particular test_engine_api.py) iterates exhaustively, so the process-global
registry stays compatible with the rest of the suite.
"""

from __future__ import annotations

import importlib

import pytest

import engine_api
from engine_api import KINDS, available, registry
from engine_api.registry import Registry, iter_registered
from engine_api.registry import provider as provider_decorator

# kinds never fully iterated by the pre-existing suite
THROWAWAY_KIND = "calibrator"
THROWAWAY_KIND2 = "embedder"


def test_kinds_tuple_unique_and_closed():
    assert isinstance(KINDS, tuple)
    assert len(KINDS) == len(set(KINDS))
    assert "source" in KINDS and "gate" in KINDS and "preprocessor" in KINDS


def test_register_unknown_kind_raises_keyerror_listing_kinds():
    with pytest.raises(KeyError) as exc:
        registry.register("zzz-not-a-kind", "x", lambda: None)
    msg = str(exc.value)
    assert "unknown capability kind" in msg
    assert "known" in msg
    assert "source" in msg  # the message lists the known kinds


def test_create_unknown_name_keyerror_lists_alternatives_for_kind():
    with pytest.raises(KeyError) as exc:
        registry.create(THROWAWAY_KIND, "zzz_does_not_exist")
    msg = str(exc.value)
    assert "no provider registered" in msg
    assert "zzz_does_not_exist" in msg
    # lists the names actually available under that kind
    for name in registry.names(THROWAWAY_KIND):
        assert name in msg


def test_create_unknown_name_in_kind_without_providers_lists_empty():
    # 'geo' has no providers registered by any test -> available: []
    if registry.names("geo"):
        pytest.skip("geo kind already populated by another test")
    with pytest.raises(KeyError) as exc:
        registry.create("geo", "zzz_missing")
    assert "available: []" in str(exc.value)


def test_reregister_same_kind_name_replaces_factory():
    registry.register(THROWAWAY_KIND, "zzz_swap", lambda: "first")
    assert registry.create(THROWAWAY_KIND, "zzz_swap") == "first"
    registry.register(THROWAWAY_KIND, "zzz_swap", lambda: "second")
    assert registry.create(THROWAWAY_KIND, "zzz_swap") == "second"
    assert ("calibrator", "zzz_swap") in registry


def test_create_passes_config_kwargs_through():
    captured = {}

    def factory(**config):
        captured.update(config)
        return object()

    registry.register(THROWAWAY_KIND, "zzz_cfg", factory)
    obj = registry.create(THROWAWAY_KIND, "zzz_cfg", a=1, b="x", nested={"k": [2]})
    assert obj is not None
    assert captured == {"a": 1, "b": "x", "nested": {"k": [2]}}


def test_factory_exception_propagates_untouched():
    def boom(**config):
        raise ValueError("factory exploded")

    registry.register(THROWAWAY_KIND, "zzz_boom", boom)
    with pytest.raises(ValueError, match="factory exploded"):
        registry.create(THROWAWAY_KIND, "zzz_boom")


def test_register_non_callable_accepted_create_then_typeerror():
    # Registry does not validate callables at register time (current behavior)
    registry.register(THROWAWAY_KIND, "zzz_notcallable", "i-am-not-callable")
    with pytest.raises(TypeError):
        registry.create(THROWAWAY_KIND, "zzz_notcallable")


def test_names_sorted():
    registry.register(THROWAWAY_KIND2, "zzz_b", lambda: None)
    registry.register(THROWAWAY_KIND2, "zzz_a", lambda: None)
    registry.register(THROWAWAY_KIND2, "zzz_c", lambda: None)
    names = registry.names(THROWAWAY_KIND2)
    assert names == sorted(names)
    for n in ("zzz_a", "zzz_b", "zzz_c"):
        assert n in names


def test_names_unknown_kind_returns_empty_list():
    assert registry.names("zzz-unknown-kind") == []


def test_contains_true_and_false():
    assert ("cache", "local") in registry
    assert ("memory", "local") in registry
    assert ("cache", "zzz_never_registered") not in registry
    # unknown kind -> no names -> False (no KeyError)
    assert ("zzz-unknown-kind", "x") not in registry


def test_available_for_every_kind_returns_single_key_dict():
    for kind in KINDS:
        out = available(kind)
        assert set(out) == {kind}
        assert out[kind] == registry.names(kind)


def test_available_keys_equal_kinds():
    assert set(available()) == set(KINDS)


def test_iter_registered_covers_everything_in_available():
    expected = {(k, n) for k, ns in available().items() for n in ns}
    assert set(iter_registered()) == expected
    # and it is an iterator-friendly iterable
    assert len(list(iter_registered())) == len(expected)


def test_registry_singleton_identity_across_imports():
    assert engine_api.registry is registry
    fresh = importlib.import_module("engine_api.registry")
    assert fresh.registry is registry
    import sakurascore
    assert sakurascore.registry is registry
    # a brand-new Registry is NOT the singleton
    assert Registry() is not registry


def test_provider_decorator_registers_and_returns_factory():
    @provider_decorator(THROWAWAY_KIND, "zzz_decorated")
    def my_factory(**config):
        return {"decorated": True, **config}

    assert (THROWAWAY_KIND, "zzz_decorated") in registry
    out = registry.create(THROWAWAY_KIND, "zzz_decorated", x=2)
    assert out == {"decorated": True, "x": 2}


def test_create_positional_kind_name_only():
    # create(kind, name, /, **config) – kind/name are positional-only
    registry.register(THROWAWAY_KIND, "zzz_pos", lambda: 42)
    assert registry.create(THROWAWAY_KIND, "zzz_pos") == 42


def test_real_provider_kinds_present_after_import():
    # conftest imports providers; all 27 real registrations must be there
    for kind, name in [
        ("source", "reddit"), ("source", "youtube"), ("source", "anime_metadata"),
        ("source", "reach_reddit"), ("source", "retail"),
        ("extractor", "web_page"), ("router", "multi_channel"),
        ("store", "local_graph"), ("store", "dgraph"),
        ("memory", "local"), ("memory", "zep"),
        ("timeseries", "search_trends"), ("timeseries", "wiki_pageviews"),
        ("sentiment", "transformer"), ("text", "indic"),
        ("uncertainty", "conformal_regressor"), ("gate", "data_readiness"),
        ("simulator", "oasis_swarm"), ("simulator", "mirofish_service"),
        ("evaluator", "factual_consistency"), ("scheduler", "prefect"),
        ("cache", "local"), ("cache", "redis"), ("limiter", "token_bucket"),
        ("normalizer", "trend_growth"), ("app", "decision_api"),
        ("ui", "decision_dashboard"),
    ]:
        assert (kind, name) in registry, f"missing {kind}/{name}"
