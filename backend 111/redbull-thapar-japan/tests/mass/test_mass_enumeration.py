"""Mass enumeration — deterministic bulk loops over pure pipeline functions.

Every loop counts its enumerated cases; each test asserts its internal counter
matches the documented constant, and ENUMERATED_CASES is the module total.
Failures are aggregated so one bad case does not hide the rest.
"""
from __future__ import annotations

import random
import re

from src.intelligence.cultural_compat.engine import (ADULT_TAGS,
                                                     COVIEW_FRICTION_TAGS,
                                                     HIGH_RISK_TAGS,
                                                     MODERATE_RISK_TAGS,
                                                     CulturalCompatibilityEngine)
from src.intelligence.localization_econ.engine import (REACH_MULTIPLIERS,
                                                       LocalizationEconomicsEngine,
                                                       format_inr)
from src.scoring.engine import ScoringEngine, grade_for

# per-loop constants
GRADE_INTS = 101
GRADE_FLOATS = 11 * 50                # 11 boundaries x 50 perturbations
PERCENTILE_POOLS = 360
PERCENTILE_QUERIES = 75               # 360*75 = 27_000 cases
CULTURAL_SUBSETS = 2_500
CBFC_TAGS = 20
CBFC_RANKS = 51                       # ranks 0..100 step 2 -> 20*51 = 1_020
LOCAL_FORMATS = 6
LOCAL_EPS = 11
LOCAL_DUR = 7                         # 6*11*7 = 462 cases
NORM_CASES = 1_000
FORMAT_INR_CASES = 18_000

ENUMERATED_CASES = (GRADE_INTS + GRADE_FLOATS
                    + PERCENTILE_POOLS * PERCENTILE_QUERIES
                    + CULTURAL_SUBSETS + CBFC_TAGS * CBFC_RANKS
                    + LOCAL_FORMATS * LOCAL_EPS * LOCAL_DUR
                    + NORM_CASES + FORMAT_INR_CASES)

E = ScoringEngine()
CUL = CulturalCompatibilityEngine()
ECO = LocalizationEconomicsEngine()
VALID_RATINGS = {"U", "U/A 7+", "U/A 13+", "A risk / U/A 16+", "A (Adults Only)"}


def _fail(failures, counter, msg):
    if len(failures) < 25:                       # cap detail, keep counting
        failures.append(f"#{counter}: {msg}")


# ------------------------------------------------------------------ grade_for
def test_mass_grade_for():
    counter = 0
    failures = []
    for score in range(0, 101):
        counter += 1
        expected = ("S" if score >= 80 else "A" if score >= 70
                    else "B" if score >= 60 else "C" if score >= 45 else "D")
        got = grade_for(score)
        if got != expected:
            _fail(failures, counter, f"{score} -> {got}, want {expected}")
    boundaries = [0, 1, 44, 45, 59, 60, 69, 70, 79, 80, 100]
    for b in boundaries:
        for i in range(50):
            delta = (i // 2 + 1) * 0.001
            s = b - delta if i % 2 == 0 else b + delta
            counter += 1
            expected = ("S" if s >= 80 else "A" if s >= 70 else "B" if s >= 60
                        else "C" if s >= 45 else "D")
            got = grade_for(s)
            if got != expected:
                _fail(failures, counter, f"{s!r} -> {got}, want {expected}")
    assert counter == GRADE_INTS + GRADE_FLOATS == 651
    assert not failures, failures


# ----------------------------------------------------------------- percentile
def test_mass_percentile_bounds_and_monotonicity():
    rng = random.Random(20260224)
    counter = 0
    failures = []
    for _ in range(PERCENTILE_POOLS):
        pool = [round(rng.uniform(-100, 100), 3)
                for _ in range(rng.randint(1, 40))]
        queries = sorted(round(rng.uniform(-120, 120), 3)
                         for _ in range(PERCENTILE_QUERIES))
        prev = None
        for q in queries:
            counter += 1
            p = E.percentile(pool, q)
            if not (0.0 <= p <= 100.0):
                _fail(failures, counter, f"pool={pool[:5]} q={q} p={p} out of range")
            if prev is not None and p < prev:
                _fail(failures, counter, f"not monotone at q={q}: {prev} -> {p}")
            prev = p
    assert counter == PERCENTILE_POOLS * PERCENTILE_QUERIES == 27_000
    assert not failures, failures


# ---------------------------------------------- cultural friction-tag subsets
def test_mass_cultural_subset_enumeration():
    rng = random.Random(42)
    friction_tags = sorted(COVIEW_FRICTION_TAGS)
    ranks = [10, 49, 50, 90]
    counter = 0
    failures = []
    for _ in range(CULTURAL_SUBSETS):
        k = rng.randint(0, 6)
        chosen = rng.sample(friction_tags, k)
        tags = [(t, rng.choice(ranks)) for t in chosen]
        genres = rng.sample(["Action", "Horror", "Comedy", "Ecchi"], rng.randint(0, 2))
        p1 = CUL.evaluate(genres=genres, tags=tags, is_adult=False,
                          format="TV", episodes=12)
        p2 = CUL.evaluate(genres=genres, tags=tags, is_adult=False,
                          format="TV", episodes=12)
        counter += 1
        if not (0 <= p1.family_co_viewing_friction <= 100):
            _fail(failures, counter,
                  f"friction {p1.family_co_viewing_friction} out of bounds: {tags}")
        if p1 != p2:
            _fail(failures, counter, f"non-deterministic: {tags}")
        if p1.cbfc_rating_estimate not in VALID_RATINGS:
            _fail(failures, counter, f"bad rating {p1.cbfc_rating_estimate!r}")
        if p1.sensitivity_triggers != sorted(set(p1.sensitivity_triggers)):
            _fail(failures, counter, "triggers not sorted+deduped")
    assert counter == CULTURAL_SUBSETS == 2_500
    assert not failures, failures


# ----------------------------------------------------------- CBFC ladder sweep
RISK_TAGS = sorted(set(HIGH_RISK_TAGS) | set(MODERATE_RISK_TAGS) | set(ADULT_TAGS)
                   | {"Religion", "Mythology"})


def test_mass_cbfc_ladder():
    counter = 0
    failures = []
    assert len(RISK_TAGS) == CBFC_TAGS
    for tag in RISK_TAGS:
        for rank in range(0, 101, 2):
            counter += 1
            p = CUL.evaluate(genres=["Action"], tags=[(tag, rank)],
                             is_adult=False, format="TV", episodes=12)
            if p.cbfc_rating_estimate not in VALID_RATINGS:
                _fail(failures, counter, f"{tag}@{rank} -> {p.cbfc_rating_estimate!r}")
            if not (0 <= p.family_co_viewing_friction <= 100):
                _fail(failures, counter, f"{tag}@{rank} friction out of bounds")
            if not (0 <= p.overall_cultural_fit <= 100):
                _fail(failures, counter, f"{tag}@{rank} overall out of bounds")
    assert counter == CBFC_TAGS * CBFC_RANKS == 1_020
    assert not failures, failures


# ------------------------------------------------------- localization grid
def test_mass_localization_grid():
    counter = 0
    failures = []
    formats = ["TV", "MOVIE", "movie", "OVA", "", None]
    eps_values = [0, 1, 6, 12, 13, 24, 25, 60, 61, 100, 500]
    dur_values = [0, 1, 24, 25, 105, 106, 300]
    modes = list(REACH_MULTIPLIERS)
    for fmt in formats:
        for eps in eps_values:
            for dur in dur_values:
                counter += 1
                r = ECO.evaluate(sakura_score=50, format=fmt, episodes=eps,
                                 duration_min=dur)
                where = f"{fmt}/{eps}/{dur}"
                if r.total_minutes <= 0:
                    _fail(failures, counter, f"{where}: total_minutes={r.total_minutes}")
                if [p.mode for p in r.plans] != modes:
                    _fail(failures, counter, f"{where}: plan order broken")
                if not all(p.cost_inr > 0 for p in r.plans):
                    _fail(failures, counter, f"{where}: non-positive cost")
                if r.recommended_mode not in modes:
                    _fail(failures, counter, f"{where}: bad rec {r.recommended_mode}")
                if not all(p.cost_per_reach_unit == round(p.cost_inr / p.reach_multiplier, 2)
                           for p in r.plans):
                    _fail(failures, counter, f"{where}: cost_per_reach_unit mismatch")
    assert counter == LOCAL_FORMATS * LOCAL_EPS * LOCAL_DUR == 462
    assert not failures, failures


# ------------------------------------------------------------------- _norm
def test_mass_norm_idempotent():
    rng = random.Random(31337)
    counter = 0
    failures = []
    pattern = re.compile(r"^[a-z0-9 ]*$")
    for _ in range(NORM_CASES):
        s = "".join(chr(rng.randrange(0x21, 0x2FFF))
                    for _ in range(rng.randint(0, 20)))
        counter += 1
        from src.app import _norm
        once = _norm(s)
        if _norm(once) != once:
            _fail(failures, counter, f"not idempotent for {s!r} -> {once!r}")
        if not pattern.match(once):
            _fail(failures, counter, f"charset violation for {s!r} -> {once!r}")
    assert counter == NORM_CASES == 1_000
    assert not failures, failures


# --------------------------------------------------------------- format_inr
def test_mass_format_inr():
    rng = random.Random(777)
    counter = 0
    failures = []
    for _ in range(FORMAT_INR_CASES):
        amount = rng.randrange(-10 ** 9, 10 ** 9 + 1)
        counter += 1
        try:
            out = format_inr(amount)
        except Exception as exc:                     # pragma: no cover
            _fail(failures, counter, f"{amount} raised {exc!r}")
            continue
        if not (isinstance(out, str) and out.startswith("₹") and len(out) > 1):
            _fail(failures, counter, f"{amount} -> {out!r}")
        elif amount >= 1_00_00_000 and not out.endswith(" Cr"):
            _fail(failures, counter, f"{amount} -> {out!r} expected Cr")
        elif 1_00_000 <= amount < 1_00_00_000 and not out.endswith(" L"):
            _fail(failures, counter, f"{amount} -> {out!r} expected L")
        elif 0 <= amount < 1_00_000 and ("Cr" in out or out.endswith(" L")):
            _fail(failures, counter, f"{amount} -> {out!r} expected plain")
    assert counter == FORMAT_INR_CASES == 18_000
    assert not failures, failures


def test_module_total():
    assert ENUMERATED_CASES == 651 + 27_000 + 2_500 + 1_020 + 462 + 1_000 + 18_000
    assert ENUMERATED_CASES == 50_633
