# SakuraScore India - Modular Research Kernel

Whitewashed, capability-oriented adapters over 20 open-source research
repositories, behind a **neutral engine contract** so a pre-existing engine
can plug them in without touching upstream APIs.

```
+----------------------------------------------------------------------------------+
|  your engine  --->  engine_api (contracts)  --->  providers (adapters)            |
|                     protocols, types,        one module per capability area,     |
|                     lazy plugin registry     lazy imports from external/ clones  |
+----------------------------------------------------------------------------------+
```

Nothing upstream is copied or rebranded: `src/` holds original adapter code
only, each module imports its clone from `external/<repo>` at call time.
Full attribution, licenses and pinned revisions: **[NOTICE](NOTICE)**.

## Layout

```
engine_api/     Neutral contract: types.py, protocols.py, registry.py
providers/      Adapters (lazy factories registered with engine_api.registry)
external/       20 shallow clones, consumed in place (licenses intact)
tests/          Behavior + contract tests (pytest)
NOTICE          Third-party attribution for all 20 repos
```

## Quick start (engine integration)

```python
import sys; sys.path.insert(0, "src")
from engine_api import registry, Query, available

available()
# {'source': ['anime_metadata', 'reddit', 'youtube', 'reach_reddit', 'retail'], ...}

# Evidence ingestion
meta = registry.create("source", "anime_metadata")
evidence = meta.fetch(Query(text="Jujutsu Kaisen", limit=5))

# Forecasting with guaranteed intervals + readiness gating (Features 41/49)
import numpy as np
model = registry.create("uncertainty", "conformal_regressor", confidence_level=0.9)
model.fit(X_train, y_train)
ivals = model.interval(X_test, alpha=0.10)          # -> list[Interval]

gate = registry.create("gate", "data_readiness", min_samples=30)
fc = gate.forecast("box_office_inr", point=5e6, interval=ivals[0], n_samples=12)
fc.ready     # False -> opportunity score only, no forecast (deck rule)
```

HTTP + UI glue (Features 71-75, 80):

```python
app = registry.create("app", "decision_api", engine_fetch=my_fetch)   # FastAPI
dash = registry.create("ui", "decision_dashboard")
dash.render_directives(directives)                                    # Streamlit
```

## Provider map (capability kind / name -> upstream repo)

| Kind | Name | Upstream clone | Purpose (dossier feature) |
|------|------|----------------|---------------------------|
| source | `anime_metadata` | jikanpy | IP metadata, studio lineage (11-16) |
| source | `reddit` | praw | Thread + comment ingestion (5, 32-38) |
| source | `youtube` | yt-dlp | Trailer metadata, view velocity (25-30, 40) |
| source | `reach_reddit` | Agent-Reach | Reddit via multi-backend router (5, 63) |
| source | `retail` | scrapy | Price/stock scraping (6, 7, 37, 51) |
| extractor | `web_page` | crawl4ai | JS-rendered page -> markdown (1, 3, 8) |
| router | `multi_channel` | Agent-Reach | 14-channel research routing (63, 67) |
| store | `local_graph` | (built-in) | Offline IP graph + provenance |
| store | `dgraph` | dgraph | Persistent IP graph (10, 11, 14, 76) |
| memory | `local` | (built-in) | Offline agent memory |
| memory | `zep` | zep | Long-term memory / Graph RAG (11-17) |
| timeseries | `search_trends` | pytrends | Regional search interest (2, 31, 41) |
| timeseries | `wiki_pageviews` | python-mwviews | Attention baseline (4) |
| normalizer | `trend_growth` | pytrends (helper) | De-trend vs growth index (2) |
| sentiment | `transformer` | transformers | Multilingual sentiment (24, 33) |
| text | `indic` | indic_nlp_library | Hindi/Tamil/Telugu normalization (32) |
| uncertainty | `conformal_regressor` | MAPIE | 90% prediction intervals (41) |
| gate | `data_readiness` | (built-in) | Block thin-data forecasts (49) |
| simulator | `oasis_swarm` | camel-ai/oasis | Grounded multi-agent society (21-23, 44, 50) |
| simulator | `mirofish_service` | MiroFish (HTTP only, AGPL) | External swarm bridge |
| evaluator | `factual_consistency` | deepeval | Hallucination/fidelity audit (46, 78) |
| scheduler | `prefect` | prefect | Continuous research cadence (61-70) |
| cache | `local` / `redis` | redis-py | Response caching (1, 10, 68) |
| limiter | `token_bucket` | redis-py | API throttling (68) |
| app | `decision_api` | fastapi | REST glue for the engine |
| ui | `decision_dashboard` | streamlit | Decision/radar dashboard (71-75, 80) |

## Design rules

1. **Engine depends on `engine_api` only** - never on upstream imports.
2. **Everything is lazy**: `registry.create` triggers upstream imports;
   importing `providers` registers factories without touching heavy deps.
3. **ProviderError** is the single failure type with actionable messages
   (missing credentials, unreachable service, missing clone).
4. **Provenance first**: every `Evidence` carries source, URL, timestamp and
   a SHA-256 `content_hash` for the audit ledger.
5. **Licensing**: MiroFish (AGPL) is bridged over HTTP only; all other
   clones are Apache/MIT/BSD/Unlicense - see `NOTICE`.

## Running the tests

```bash
pip install pytest httpx fastapi requests numpy scikit-learn
PYTHONPATH=src python -m pytest tests/ -q
# 25 passed
```

Network-backed providers (reddit, youtube, dgraph, zep, mirofish, oasis)
are covered by construction/contract tests; live calls need credentials or
a running service as documented in `NOTICE`.
