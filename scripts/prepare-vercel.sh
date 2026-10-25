#!/bin/bash
# Build the serverless python backend bundle (api/_backend) from the full repo.
# The backend source is small (~10 MB: src + processed CSVs + modules/src);
# the 6.4G external clones and the raw pulls stay out.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BE="$ROOT/backend 111/redbull-thapar-japan"
OUT="$ROOT/api/_backend"

[ -d "$BE/src" ] || { echo "backend source not found at: $BE" >&2; exit 1; }

rm -rf "$OUT"
mkdir -p "$OUT/data"
cp -R "$BE/src" "$OUT/src"
cp -R "$BE/data/processed" "$OUT/data/processed"
cp -R "$BE/data/reference" "$OUT/data/reference"
cp -R "$BE/data/casting" "$OUT/data/casting"
cp -R "$BE/modules/src" "$OUT/modules_src"
cp "$ROOT/scripts/backend/greenlight.py" "$OUT/greenlight.py"
cp "$ROOT/scripts/backend/worker.py" "$OUT/worker.py"
cp "$ROOT/scripts/backend/casting.py" "$OUT/casting.py"
cp "$ROOT/scripts/backend/sketch.py" "$OUT/sketch.py"
find "$OUT" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$OUT" -name "*.pyc" -delete 2>/dev/null || true

echo "api/_backend built: $(du -sh "$OUT" | cut -f1)"
