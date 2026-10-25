#!/bin/bash
# Build the serverless python backend bundle (api/_backend) from the full repo.
# The backend source is small (~10 MB: src + processed CSVs + modules/src);
# the 6.4G external clones and the raw pulls stay out.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BE="$ROOT/backend 111/redbull-thapar-japan"
OUT="$ROOT/api/_backend"

[ -d "$BE/src" ] || { echo "backend source not found at: $BE" >&2; exit 1; }

# api/_backend is COMMITTED to git and shipped by .vercelignore on purpose:
# a GitHub-connected Vercel build never runs this script (and .vercelignore
# keeps `backend 111` out of the deployment), so the bundle must already exist
# in the repository for the python functions to be able to import it.
rm -rf "$OUT"
mkdir -p "$OUT/data" "$OUT/modules"
cp -R "$BE/src" "$OUT/src"
cp -R "$BE/data/processed" "$OUT/data/processed"
cp -R "$BE/data/reference" "$OUT/data/reference"
cp -R "$BE/data/casting" "$OUT/data/casting"
# modules/src MUST land at modules/src (not modules_src): greenlight.py builds
# MODULES_SRC = BACKEND/"modules"/"src" and module_inventory() imports the
# provider registry from there. Heavier optional artifacts are skipped.
cp -R "$BE/modules/src" "$OUT/modules/src"
cp "$ROOT/scripts/backend/greenlight.py" "$OUT/greenlight.py"
cp "$ROOT/scripts/backend/worker.py" "$OUT/worker.py"
cp "$ROOT/scripts/backend/casting.py" "$OUT/casting.py"
cp "$ROOT/scripts/backend/sketch.py" "$OUT/sketch.py"
# CNN weights (local torch path only; harmless 0.5 MB, and keeps parity with
# the local dev bundle). Heuristics are the serverless path.
if [ -d "$BE/data/sketch_model" ]; then cp -R "$BE/data/sketch_model" "$OUT/data/sketch_model"; fi
find "$OUT" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$OUT" -name "*.pyc" -delete 2>/dev/null || true

echo "api/_backend built: $(du -sh "$OUT" | cut -f1)"
