"""Shared fixtures/helpers for SakuraScore simulation tests."""

from __future__ import annotations

import copy
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def minimal_valid_config() -> dict:
    """Smallest config that must validate and run. Inline evidence, 2 segments,
    2 scenarios, tiny population, no variability ensemble."""
    return {
        "schema_version": "1.0",
        "ip_id": "test-ip",
        "title": "Test IP",
        "experiment_id": "test-experiment",
        "media_type": "anime_film",
        "genre": "drama",
        "evidence": [
            {
                "id": "src-1",
                "title": "A public report",
                "url": "https://example.com/report",
                "publisher": "Example Publisher",
                "date": "2025-06",
                "finding": "Some observed finding used for segment grounding.",
                "type": "news",
                "region": "India",
                "label": "observed",
                "quality": "high",
            }
        ],
        "audience_segments": [
            {
                "id": "seg-a",
                "label": "Segment A (subs-tolerant)",
                "size_share": 0.6,
                "base_interest": 0.7,
                "discovery_base": 0.2,
                "view_info_prob": 0.8,
                "share_prob": 0.2,
                "discuss_prob": 0.25,
                "language_affinity": {"en": 0.8, "ja": 0.3, "hi": 0.1},
                "channel_affinity": {"streaming": 0.8, "social": 0.5},
                "evidence_ids": ["src-1"],
                "notes": "hypothesis",
            },
            {
                "id": "seg-b",
                "label": "Segment B (regional-first)",
                "size_share": 0.4,
                "base_interest": 0.6,
                "discovery_base": 0.15,
                "view_info_prob": 0.7,
                "share_prob": 0.3,
                "discuss_prob": 0.3,
                "language_affinity": {"hi": 0.7, "ta": 0.2, "en": 0.15},
                "channel_affinity": {"streaming": 0.6, "social": 0.7, "tv": 0.4},
                "evidence_ids": ["src-1"],
                "notes": "hypothesis",
            },
        ],
        "scenarios": [
            {
                "id": "baseline",
                "label": "Baseline",
                "is_baseline": True,
                "counterfactual": True,
                "languages_available": ["ja", "en"],
                "marketing_reach": {"streaming": 1.0, "social": 1.0},
            },
            {
                "id": "dub",
                "label": "Regional dub",
                "languages_available": ["ja", "en", "hi", "ta"],
                "marketing_reach": {"streaming": 1.0, "social": 1.0},
            },
        ],
        "simulation": {
            "agent_count": 12,
            "rounds": 4,
            "seed": 42,
        },
    }


def example_config_path() -> str:
    return os.path.join(REPO_ROOT, "configs", "example_experiment.json")


def mutated_config(**overrides) -> dict:
    """Return a minimal valid config with top-level key overrides applied."""
    cfg = minimal_valid_config()
    cfg.update(copy.deepcopy(overrides))
    return cfg
