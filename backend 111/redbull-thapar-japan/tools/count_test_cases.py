#!/usr/bin/env python3
"""Count executed test cases across both suites.

Three layers are summed:
  1. pytest-collected tests (parametrization already expanded by pytest)
  2. hypothesis property examples actually executed (parsed from
     --hypothesis-show-statistics output saved by run_mega_tests.sh)
  3. deterministic mass-enumeration checks (ENUMERATED_CASES constants
     declared — and self-asserted — inside the mass test modules)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / ".test_results"

# Hypothesis stats line: "- 100 passing, 0 failing, and 0 invalid test cases"
HYP_EXAMPLE_RE = re.compile(
    r"^\s*- (\d[\d,]*) passing, (\d[\d,]*) failing, and (\d[\d,]*) invalid", re.M)
PASSED_RE = re.compile(r"^([\d,]+) passed", re.M)
ENUM_RE = re.compile(r"^ENUMERATED_CASES\s*=\s*(\d+)", re.M)


def parse_suite(txt: Path) -> tuple[int, int, int, int]:
    """Return (pytest_cases, property_examples, failed, errors)."""
    if not txt.exists():
        return 0, 0, 0, 0
    raw = txt.read_text(encoding="utf-8", errors="replace")
    pytest_cases = sum(int(m.replace(",", "")) for m in PASSED_RE.findall(raw))
    examples = sum(
        int(p.replace(",", "")) + int(f.replace(",", "")) + int(i.replace(",", ""))
        for p, f, i in HYP_EXAMPLE_RE.findall(raw))
    failed = len(re.findall(r"^FAILED ", raw, re.M)) + len(
        re.findall(r"^ERROR ", raw, re.M))
    return pytest_cases, examples, failed, 0


def _module_enum_value(path: Path) -> int:
    """Exec a mass-test module in a scratch namespace and read ENUMERATED_CASES.

    The constants are arithmetic over named sub-constants, so they must be
    evaluated (module top level only defines constants + test functions;
    nothing networky or heavy runs at import).
    """
    import runpy
    ns = runpy.run_path(str(path))
    return int(ns["ENUMERATED_CASES"])


def enumerated_constants() -> tuple[int, list[str]]:
    # mass modules import from src/ or modules/src — put both on sys.path
    for p in (ROOT / "tests", ROOT, ROOT / "modules" / "src"):
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)
    total, files = 0, []
    for pattern in ("tests/mass/**/*.py", "modules/tests/mass/**/*.py"):
        for f in sorted(ROOT.glob(pattern)):
            if f.name == "__init__.py":
                continue
            try:
                val = _module_enum_value(f)
            except KeyError:
                continue  # module without an ENUMERATED_CASES constant
            except Exception as exc:  # unparsable module shouldn't kill the count
                print(f"    WARN could not evaluate {f}: {exc}")
                continue
            total += val
            files.append(f"{f.relative_to(ROOT)}: {val:,}")
    return total, files


def main() -> int:
    src_txt = RESULTS / "src_suite.txt"
    mod_txt = RESULTS / "modules_suite.txt"

    src_cases, src_ex, src_fail, _ = parse_suite(src_txt)
    mod_cases, mod_ex, mod_fail, _ = parse_suite(mod_txt)
    enum_total, enum_files = enumerated_constants()

    hypothesis_total = src_ex + mod_ex
    pytest_total = src_cases + mod_cases
    grand = pytest_total + hypothesis_total + enum_total

    print("Executed test-case accounting")
    print("=" * 56)
    print(f"src suite      : {src_cases:>8,} pytest cases")
    print(f"modules suite  : {mod_cases:>8,} pytest cases")
    print(f"property-based : {hypothesis_total:>8,} hypothesis examples "
          f"(src {src_ex:,} + modules {mod_ex:,})")
    print(f"mass-enumerated: {enum_total:>8,} deterministic checks")
    for line in enum_files:
        print(f"    {line}")
    print("-" * 56)
    print(f"GRAND TOTAL    : {grand:>8,} executed test cases")
    target_met = "YES" if grand >= 100_000 else "NO"
    print(f"100k target    : {target_met}")
    fails = src_fail + mod_fail
    if fails:
        print(f"WARNING: {fails} failed/errored tests in the saved runs")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
