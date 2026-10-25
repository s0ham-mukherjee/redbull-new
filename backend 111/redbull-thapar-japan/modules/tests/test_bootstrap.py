"""Tests for providers._bootstrap: ensure_paths, REPO_PATHS, ProviderError."""

from __future__ import annotations

import sys

import pytest

import providers._bootstrap as bootstrap
from providers._bootstrap import EXTERNAL, REPO_PATHS, ProviderError, ensure_paths


def test_provider_error_is_runtime_error_subclass():
    assert issubclass(ProviderError, RuntimeError)
    assert isinstance(ProviderError("boom"), RuntimeError)
    assert str(ProviderError("boom")) == "boom"


def test_ensure_paths_unknown_repo_keyerror_lists_known():
    with pytest.raises(KeyError) as exc:
        ensure_paths("zzz-not-a-repo")
    msg = str(exc.value)
    assert "unknown cloned repo" in msg
    assert "zzz-not-a-repo" in msg
    # message lists the known repos
    assert "jikanpy" in msg and "prefect" in msg


def test_ensure_paths_missing_clone_dir_filenotfound(monkeypatch, tmp_path):
    monkeypatch.setattr(bootstrap, "EXTERNAL", tmp_path)  # empty tmp dir
    with pytest.raises(FileNotFoundError) as exc:
        ensure_paths("jikanpy")
    assert "clone missing" in str(exc.value)
    assert "jikanpy" in str(exc.value)


def test_ensure_paths_idempotent_no_duplicate_sys_path_entries():
    path = str(EXTERNAL / "plotly")
    snapshot = list(sys.path)
    try:
        while path in sys.path:  # start from a clean slate for this repo
            sys.path.remove(path)
        ensure_paths("plotly")
        assert sys.path.count(path) == 1
        ensure_paths("plotly")
        ensure_paths("plotly")
        assert sys.path.count(path) == 1
    finally:
        sys.path[:] = snapshot  # providers re-add paths on demand via ensure_paths


def test_every_repo_in_repo_paths_maps_to_str_paths(tmp_path):
    # Use a fake external tree so we do not pollute sys.path with 50+ real
    # clone roots mid-suite.
    fake_external = tmp_path / "external"
    original_external = bootstrap.EXTERNAL
    snapshot = list(sys.path)
    try:
        for repo, roots in REPO_PATHS.items():
            for rel in roots:
                (fake_external / repo / rel).mkdir(parents=True, exist_ok=True)
        bootstrap.EXTERNAL = fake_external
        for repo, roots in REPO_PATHS.items():
            ensure_paths(repo)
            for rel in roots:
                expected = str(fake_external / repo / rel) if rel != "." else str(fake_external / repo)
                assert expected in sys.path, f"{repo}/{rel} missing from sys.path"
                assert isinstance(expected, str)
    finally:
        bootstrap.EXTERNAL = original_external
        sys.path[:] = snapshot


def test_repo_paths_shape():
    assert isinstance(REPO_PATHS, dict)
    assert len(REPO_PATHS) >= 50
    for repo, roots in REPO_PATHS.items():
        assert isinstance(repo, str) and repo
        assert isinstance(roots, tuple)
        assert all(isinstance(r, str) and r for r in roots)


def test_external_root_points_at_project_external():
    assert EXTERNAL.name == "external"
    assert EXTERNAL.is_dir()


def test_repo_paths_clones_exist_on_disk():
    # environment guarantee: every REPO_PATHS entry has a clone on disk
    for repo in ("jikanpy", "pytrends", "MAPIE", "prefect", "Agent-Reach"):
        assert (EXTERNAL / repo).is_dir(), f"clone for {repo} missing"


def test_ensure_paths_accepts_multiple_repos_at_once():
    snapshot = list(sys.path)
    try:
        ensure_paths("vaderSentiment", "networkx")
        assert str(EXTERNAL / "vaderSentiment") in sys.path
        assert str(EXTERNAL / "networkx") in sys.path
    finally:
        sys.path[:] = snapshot
