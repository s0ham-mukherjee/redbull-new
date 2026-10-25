"""Conformal uncertainty & readiness gating (upstream clone: scikit-learn-contrib/MAPIE, BSD-3).

Exposed capabilities:
- ``uncertainty`` / ``conformal_regressor`` - prediction intervals (Feature 41).
- ``gate`` / ``data_readiness`` - blocks forecasts without enough target data (Feature 49).
"""

from __future__ import annotations

from typing import Any, Sequence

from engine_api import Forecast, Interval, provider

from ._bootstrap import ProviderError, ensure_paths


def _slice(X: Any, y: Any, idx: slice) -> tuple[Any, Any]:
    """Index numpy arrays or python sequences uniformly."""
    try:
        return X[idx], y[idx]
    except TypeError:
        XL, yl = list(X), list(y)
        return XL[idx], yl[idx]


class ConformalRegressor:
    """UncertaintyEstimator wrapping MAPIE's SplitConformalRegressor (v1 API)."""

    def __init__(self, estimator: Any = None, confidence_level: float = 0.9) -> None:
        ensure_paths("MAPIE")
        self._estimator = estimator  # None -> MAPIE default (LinearRegression)
        self._confidence_level = confidence_level
        self._model: Any = None

    def fit(self, X: Any, y: Any) -> "ConformalRegressor":
        from mapie.regression import SplitConformalRegressor  # lazy upstream import

        kwargs: dict[str, Any] = {"confidence_level": self._confidence_level, "prefit": False}
        if self._estimator is not None:
            kwargs["estimator"] = self._estimator
        self._model = SplitConformalRegressor(**kwargs)

        # MAPIE v1 splits fit / conformalize: fit the base estimator on one
        # fold, compute conformity scores on a held-out calibration fold.
        n = len(X)
        if n < 8:
            self._model.fit(X, y)
            try:
                self._model.conformalize(X, y)
            except Exception:
                pass
            return self
        split = max(1, int(n * 0.8))
        X_train, y_train = _slice(X, y, slice(0, split))
        X_cal, y_cal = _slice(X, y, slice(split, n))
        self._model.fit(X_train, y_train)
        self._model.conformalize(X_cal, y_cal)
        return self

    def interval(self, X: Any, alpha: float = 0.10) -> list[Interval]:
        if self._model is None:
            raise ProviderError("ConformalRegressor.fit must be called before interval()")
        import numpy as np

        confidence = 1.0 - alpha
        # Refit lazily if requested confidence differs from the fitted one.
        if abs(confidence - self._confidence_level) > 1e-9:
            self.__init__(estimator=self._estimator, confidence_level=confidence)
            raise ProviderError(
                "confidence changed; call fit(X, y) again with the new alpha"
            )
        try:
            points, bounds = self._model.predict_interval(X)
        except Exception as exc:
            raise ProviderError(f"interval prediction failed: {exc}") from exc

        points = np.asarray(points).reshape(-1)
        bounds = np.asarray(bounds)
        # bounds shape: (n_samples, 2, n_confidence_levels)
        lower = bounds[:, 0, 0]
        upper = bounds[:, 1, 0]
        return [
            Interval(point=float(p), lower=float(lo), upper=float(up), alpha=alpha)
            for p, lo, up in zip(points, lower, upper)
        ]


class DataReadinessGate:
    """ForecastGate: refuse to forecast when historical target data is sparse."""

    def __init__(self, min_samples: int = 30) -> None:
        self.min_samples = int(min_samples)

    def ready(self, n_samples: int, min_samples: int | None = None) -> bool:
        threshold = self.min_samples if min_samples is None else int(min_samples)
        return bool(n_samples) and n_samples >= threshold

    def forecast(
        self,
        target: str,
        point: float,
        interval: Interval,
        n_samples: int,
    ) -> Forecast:
        if not self.ready(n_samples):
            return Forecast(
                target=target,
                interval=interval,
                n_calibration_samples=n_samples,
                ready=False,
                reason=(
                    f"only {n_samples} historical target samples; "
                    f"need >= {self.min_samples} - issuing opportunity score only, no forecast"
                ),
            )
        return Forecast(
            target=target,
            interval=interval,
            n_calibration_samples=n_samples,
            ready=True,
        )


@provider("uncertainty", "conformal_regressor")
def _conformal_factory(**config: Any) -> ConformalRegressor:
    return ConformalRegressor(**config)


@provider("gate", "data_readiness")
def _gate_factory(**config: Any) -> DataReadinessGate:
    return DataReadinessGate(**config)


__all__ = ["ConformalRegressor", "DataReadinessGate", "Sequence"]
