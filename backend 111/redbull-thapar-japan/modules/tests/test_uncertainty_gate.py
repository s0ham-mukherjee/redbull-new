"""DataReadinessGate matrix + ConformalRegressor against the real MAPIE clone."""

from __future__ import annotations

import numpy as np
import pytest

from engine_api import Forecast, Interval
from engine_api.protocols import ForecastGate, UncertaintyEstimator
from providers._bootstrap import ProviderError
from providers.uncertainty import ConformalRegressor, DataReadinessGate, _slice


# ---------------------------------------------------------------------------
# DataReadinessGate.ready matrix
# ---------------------------------------------------------------------------


MIN_CASES = [1, 5, 30, 100]
N_CASES = [0, 1, 4, 29, 30, 31, 100]


@pytest.mark.parametrize("min_samples", MIN_CASES)
@pytest.mark.parametrize("n", N_CASES)
def test_gate_ready_matrix(min_samples, n):
    gate = DataReadinessGate(min_samples=min_samples)
    assert gate.ready(n) == (bool(n) and n >= min_samples)


@pytest.mark.parametrize("n", [0, 1, 4, 29, 30, 31, 100])
@pytest.mark.parametrize("min_samples", MIN_CASES)
def test_gate_ready_override_beats_instance_default(min_samples, n):
    gate = DataReadinessGate(min_samples=999)
    assert gate.ready(n, min_samples=min_samples) == (bool(n) and n >= min_samples)


def test_gate_ready_zero_min_with_zero_n_still_false():
    # bool(0) is False -> n must be a truthy int, not just >= threshold
    gate = DataReadinessGate(min_samples=0)
    assert gate.ready(0) is False
    assert gate.ready(1) is True


def test_gate_ready_negative_threshold_quirk():
    # CURRENT behavior: with a negative threshold any truthy n passes,
    # including negative n (bool(-5) is True and -5 >= -10).
    gate = DataReadinessGate(min_samples=-10)
    assert gate.ready(-5) is True
    assert gate.ready(1) is True
    assert gate.ready(0) is False


def test_gate_ready_bool_input_behaves_like_int():
    gate = DataReadinessGate(min_samples=1)
    assert gate.ready(True) is True
    assert gate.ready(False) is False


def test_gate_forecast_not_ready_path():
    gate = DataReadinessGate(min_samples=30)
    iv = Interval(point=100.0, lower=70.0, upper=140.0, alpha=0.10)
    f = gate.forecast("trailer_views_30d", 100.0, iv, n_samples=12)
    assert isinstance(f, Forecast)
    assert f.ready is False
    assert f.target == "trailer_views_30d"
    assert f.interval is iv
    assert f.n_calibration_samples == 12
    assert f"need >= 30" in (f.reason or "")


def test_gate_forecast_ready_path():
    gate = DataReadinessGate(min_samples=30)
    iv = Interval(point=1.0, lower=0.5, upper=1.5)
    f = gate.forecast("target", 1.0, iv, n_samples=30)  # exactly at threshold
    assert f.ready is True
    assert f.reason is None
    assert f.n_calibration_samples == 30
    assert f.interval is iv


@pytest.mark.parametrize("min_samples,n", [(1, 0), (5, 4), (30, 29), (100, 99)])
def test_gate_forecast_blocked_one_below_threshold(min_samples, n):
    gate = DataReadinessGate(min_samples=min_samples)
    f = gate.forecast("t", 0.0, Interval(point=0, lower=0, upper=0), n)
    assert f.ready is False
    assert f"need >= {min_samples}" in f.reason


def test_gate_satisfies_protocol():
    assert isinstance(DataReadinessGate(), ForecastGate)


# ---------------------------------------------------------------------------
# ConformalRegressor (real MAPIE)
# ---------------------------------------------------------------------------


def _linear_data(n: int, seed: int):
    rng = np.random.default_rng(seed)
    X = rng.uniform(0, 10, size=(n, 2))
    y = 3 * X[:, 0] - 2 * X[:, 1] + rng.normal(0, 0.5, size=n)
    return X, y


def test_conformal_interval_before_fit_raises():
    with pytest.raises(ProviderError, match="fit must be called"):
        ConformalRegressor().interval([[1.0]])


def test_conformal_fit_small_n_with_low_confidence_lists():
    # n<8 branch: fit + conformalize both tolerate tiny samples at conf 0.5
    X, y = _linear_data(7, seed=11)
    m = ConformalRegressor(confidence_level=0.5)
    assert m.fit(X.tolist(), y.tolist()) is m
    ivs = m.interval(X.tolist(), alpha=0.5)
    assert len(ivs) == 7
    for iv in ivs:
        assert iv.lower <= iv.point <= iv.upper
        assert iv.alpha == 0.5


def test_conformal_fit_small_n_default_confidence_fit_ok_interval_fails():
    # CURRENT: at conf 0.9 the calibration fold is too small for MAPIE, the
    # conformalize error is swallowed in fit() and surfaces at interval().
    X, y = _linear_data(7, seed=12)
    m = ConformalRegressor()  # confidence_level=0.9
    assert m.fit(X.tolist(), y.tolist()) is m
    with pytest.raises(ProviderError, match="interval prediction failed"):
        m.interval(X.tolist(), alpha=0.10)


def test_conformal_fit_split_path_with_lists():
    # python sequences exercise the _slice direct-indexing path
    X, y = _linear_data(60, seed=21)
    m = ConformalRegressor(confidence_level=0.9)
    assert m.fit(X.tolist(), y.tolist()) is m
    ivs = m.interval(X.tolist(), alpha=0.10)
    assert len(ivs) == 60
    for iv in ivs:
        assert isinstance(iv, Interval)
        assert iv.lower <= iv.point <= iv.upper
        assert iv.alpha == pytest.approx(0.10)


def test_conformal_fit_split_path_with_numpy_arrays():
    X, y = _linear_data(60, seed=22)
    m = ConformalRegressor(confidence_level=0.9)
    m.fit(X, y)
    ivs = m.interval(X, alpha=0.10)
    assert len(ivs) == 60
    assert all(iv.lower <= iv.point <= iv.upper for iv in ivs)


def test_conformal_confidence_mismatch_raises():
    X, y = _linear_data(60, seed=23)
    m = ConformalRegressor(confidence_level=0.9)
    m.fit(X, y)
    with pytest.raises(ProviderError, match="confidence changed"):
        m.interval(X, alpha=0.5)


def test_conformal_confidence_mismatch_destroys_state_current_behavior():
    # CURRENT side effect (uncertainty.py:68 re-__init__): the error path
    # resets the fitted model, so even the *original* alpha no longer works.
    X, y = _linear_data(60, seed=24)
    m = ConformalRegressor(confidence_level=0.9)
    m.fit(X, y)
    with pytest.raises(ProviderError, match="confidence changed"):
        m.interval(X, alpha=0.5)
    assert m._model is None
    with pytest.raises(ProviderError, match="fit must be called"):
        m.interval(X, alpha=0.10)
    # desired behavior (state survives the rejected request) -> test_bugs.py


def test_conformal_constructed_at_conf_09_interval_alpha_10_matches():
    X, y = _linear_data(60, seed=25)
    m = ConformalRegressor(confidence_level=0.9)
    m.fit(X, y)
    ivs = m.interval(X, alpha=0.10)  # 1 - 0.10 == 0.9 -> no mismatch
    assert len(ivs) == 60


def test_conformal_coverage_on_linear_data():
    X, y = _linear_data(150, seed=26)
    m = ConformalRegressor(confidence_level=0.9)
    m.fit(X[:100], y[:100])
    ivs = m.interval(X[100:], alpha=0.10)
    truth = y[100:]
    covered = sum(iv.lower <= t <= iv.upper for iv, t in zip(ivs, truth))
    assert covered / len(truth) >= 0.75


def test_conformal_satisfies_protocol():
    assert isinstance(ConformalRegressor(), UncertaintyEstimator)


def test_conformal_via_registry(reg):
    m = reg.create("uncertainty", "conformal_regressor", confidence_level=0.5)
    assert isinstance(m, UncertaintyEstimator)


# ---------------------------------------------------------------------------
# _slice helper
# ---------------------------------------------------------------------------


def test_slice_tuples_vs_lists_vs_arrays_equivalence():
    idx = slice(2, 5)
    t = tuple(range(10))
    assert _slice(t, t, idx) == ((2, 3, 4), (2, 3, 4))
    L = list(range(10))
    assert _slice(L, L, idx) == ([2, 3, 4], [2, 3, 4])
    arr = np.arange(10)
    a, b = _slice(arr, arr, idx)
    assert a.tolist() == [2, 3, 4] and b.tolist() == [2, 3, 4]
    # mixed list/np
    a, b = _slice(L, arr, idx)
    assert a == [2, 3, 4] and b.tolist() == [2, 3, 4]


def test_slice_generator_falls_back_to_list():
    g = (i * 2 for i in range(10))
    a, b = _slice(g, range(10, 20), slice(0, 8))
    assert a == [0, 2, 4, 6, 8, 10, 12, 14]
    assert b == [10, 11, 12, 13, 14, 15, 16, 17]


def test_slice_empty_range():
    a, b = _slice([], [], slice(0, 0))
    assert a == [] and b == []
