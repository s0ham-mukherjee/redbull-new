#!/usr/bin/env bash
# SakuraScore mega test runner.
# Usage:
#   ./run_mega_tests.sh            # default profile (fast CI)
#   ./run_mega_tests.sh exhaustive # 100k+ executed test cases (property x1500)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PROFILE="${1:-default}"
OUT="$ROOT/.test_results"
mkdir -p "$OUT"

echo "=== hypothesis profile: $PROFILE ==="

echo "--- [1/2] src pipeline suite (tests/) ---"
( cd "$ROOT" && python3 -m pytest tests -q \
    --hypothesis-profile "$PROFILE" \
    --hypothesis-show-statistics \
    -p no:cacheprovider \
    | tee "$OUT/src_suite.txt" | tail -3 )

echo "--- [2/2] modules engine suite (modules/tests/) ---"
( cd "$ROOT/modules" && PYTHONPATH=src python3 -m pytest tests -q \
    --hypothesis-profile "$PROFILE" \
    --hypothesis-show-statistics \
    -p no:cacheprovider \
    | tee "$OUT/modules_suite.txt" | tail -3 )

echo "--- grand total ---"
python3 "$ROOT/tools/count_test_cases.py"
