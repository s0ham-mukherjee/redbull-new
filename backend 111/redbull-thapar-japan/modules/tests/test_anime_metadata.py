"""AnimeMetadataSource: to_ip_node projection + fetch with a fake Jikan client."""

from __future__ import annotations

import json

import pytest

from engine_api import Query
from engine_api.protocols import EvidenceSource
from providers._bootstrap import ProviderError
from providers.anime_metadata import AnimeMetadataSource

import providers.anime_metadata as amod


# ---------------------------------------------------------------------------
# to_ip_node
# ---------------------------------------------------------------------------


def test_to_ip_node_id_from_mal_id():
    node = AnimeMetadataSource.to_ip_node({"mal_id": 20, "title": "Naruto"})
    assert node.id == "mal:20"


def test_to_ip_node_missing_mal_id_gives_mal_none_current():
    # CURRENT: f"mal:{item.get('mal_id')}" -> "mal:None"
    node = AnimeMetadataSource.to_ip_node({"title": "Ghost"})
    assert node.id == "mal:None"


@pytest.mark.parametrize("typ", [None, "TV", "Movie", "OVA", "ONA", "Special"])
def test_to_ip_node_anime_type_variants(typ):
    node = AnimeMetadataSource.to_ip_node({"mal_id": 1, "title": "X", "type": typ})
    assert node.kind == "anime"


@pytest.mark.parametrize("typ", ["Manga", "Manhwa", "Light Novel", "Music", "unknown"])
def test_to_ip_node_other_types_map_to_manga(typ):
    node = AnimeMetadataSource.to_ip_node({"mal_id": 1, "title": "X", "type": typ})
    assert node.kind == "manga"


def test_to_ip_node_genres_missing_gives_empty_tuple():
    node = AnimeMetadataSource.to_ip_node({"mal_id": 1, "title": "X"})
    assert node.genres == ()
    node2 = AnimeMetadataSource.to_ip_node({"mal_id": 1, "title": "X", "genres": []})
    assert node2.genres == ()


def test_to_ip_node_genres_names_extracted():
    node = AnimeMetadataSource.to_ip_node(
        {"mal_id": 1, "title": "X", "genres": [{"name": "Action"}, {"name": "Shonen"}]})
    assert node.genres == ("Action", "Shonen")


def test_to_ip_node_genre_missing_name_defaults_empty_string():
    node = AnimeMetadataSource.to_ip_node(
        {"mal_id": 1, "title": "X", "genres": [{"mal_id": 3}, {"name": "Drama"}]})
    assert node.genres == ("", "Drama")


@pytest.mark.parametrize("studios", [None, [], [{}], [{"name": None}]])
def test_to_ip_node_studios_missing_or_empty_gives_none(studios):
    node = AnimeMetadataSource.to_ip_node({"mal_id": 1, "title": "X", "studios": studios})
    assert node.studio is None


def test_to_ip_node_studios_first_element_name():
    node = AnimeMetadataSource.to_ip_node(
        {"mal_id": 1, "title": "X", "studios": [{"name": "MAPPA"}, {"name": "Other"}]})
    assert node.studio == "MAPPA"


def test_to_ip_node_no_related_gives_none():
    node = AnimeMetadataSource.to_ip_node({"mal_id": 1, "title": "X"})
    assert node.adaptation_of is None
    node2 = AnimeMetadataSource.to_ip_node({"mal_id": 1, "title": "X", "related": []})
    assert node2.adaptation_of is None


@pytest.mark.parametrize("relation_text", ["Adaptation", "adaptation", "ADAPTATION",
                                           "Side story & adaptation notes", "Pre-adaptation"])
def test_to_ip_node_adaptation_extraction_case_insensitive(relation_text):
    node = AnimeMetadataSource.to_ip_node({
        "mal_id": 1, "title": "X",
        "related": [{"relation": relation_text,
                     "entry": [{"name": "Source Manga"}]}],
    })
    assert node.adaptation_of == "Source Manga"


def test_to_ip_node_multiple_relations_picks_adaptation():
    node = AnimeMetadataSource.to_ip_node({
        "mal_id": 1, "title": "X",
        "related": [
            {"relation": "Sequel", "entry": [{"name": "Later Season"}]},
            {"relation": "Summary", "entry": [{"name": "Recap"}]},
            {"relation": "Adaptation", "entry": [{"name": "The Manga"}]},
            {"relation": "Other adaptation", "entry": [{"name": "Later Adaptation"}]},
        ],
    })
    assert node.adaptation_of == "The Manga"


def test_to_ip_node_non_adaptation_relations_ignored():
    node = AnimeMetadataSource.to_ip_node({
        "mal_id": 1, "title": "X",
        "related": [{"relation": "Sequel", "entry": [{"name": "S2"}]}],
    })
    assert node.adaptation_of is None


def test_to_ip_node_entry_list_empty_raises_indexerror_current():
    # CURRENT (anime_metadata.py:89 `prev.get("entry", [{}])[0]`): an empty
    # entry list crashes. Desired: adaptation_of None -> test_bugs.py.
    with pytest.raises(IndexError):
        AnimeMetadataSource.to_ip_node({
            "mal_id": 1, "title": "X",
            "related": [{"relation": "Adaptation", "entry": []}],
        })


def test_to_ip_node_entry_missing_uses_default_no_crash():
    node = AnimeMetadataSource.to_ip_node({
        "mal_id": 1, "title": "X",
        "related": [{"relation": "Adaptation"}],
    })
    assert node.adaptation_of is None


def test_to_ip_node_entry_name_missing_gives_none():
    node = AnimeMetadataSource.to_ip_node({
        "mal_id": 1, "title": "X",
        "related": [{"relation": "Adaptation", "entry": [{"mal_id": 9}]}],
    })
    assert node.adaptation_of is None


def test_to_ip_node_aliases_order_and_falsy_filtered():
    node = AnimeMetadataSource.to_ip_node({
        "mal_id": 1, "title": "X",
        "title_japanese": "ナルト",
        "title_english": "Naruto",
    })
    assert node.aliases == ("ナルト", "Naruto")  # japanese first
    node2 = AnimeMetadataSource.to_ip_node({
        "mal_id": 2, "title": "Y", "title_japanese": "", "title_english": None,
    })
    assert node2.aliases == ()


def test_to_ip_node_attributes_have_leading_space_aired_from():
    # CURRENT behavior: the key is " aired_from" (leading space) – asserted
    # here so a future fix is a conscious rename.
    node = AnimeMetadataSource.to_ip_node({
        "mal_id": 1, "title": "X", "score": 8.2, "members": 1000,
        "aired": {"from": "2024-01-01T00:00:00+00:00"},
    })
    assert " aired_from" in node.attributes
    assert node.attributes[" aired_from"] == "2024-01-01T00:00:00+00:00"
    assert node.attributes["source"] == "jikan"
    assert node.attributes["score"] == 8.2
    assert node.attributes["members"] == 1000


def test_to_ip_node_attributes_aired_missing():
    node = AnimeMetadataSource.to_ip_node({"mal_id": 1, "title": "X"})
    assert node.attributes[" aired_from"] is None


def test_to_ip_node_title_str_coercion():
    node = AnimeMetadataSource.to_ip_node({"mal_id": 1, "title": None})
    assert node.title == ""
    assert AnimeMetadataSource.to_ip_node({"mal_id": 1, "title": 123}).title == "123"


# ---------------------------------------------------------------------------
# fetch with a fake Jikan client
# ---------------------------------------------------------------------------


class FakeJikan:
    def __init__(self, payload=None, error=None):
        self.payload = payload if payload is not None else {"data": []}
        self.error = error
        self.calls = []

    def search(self, search_type, text, page=None):
        self.calls.append((search_type, text, page))
        if self.error is not None:
            raise self.error
        return self.payload


def _sample_payload(n=3):
    return {"data": [
        {
            "mal_id": i,
            "url": f"https://myanimelist.net/anime/{i}",
            "title": f"Title {i}",
            "type": "TV",
            "episodes": 12 + i,
            "score": 7.5 + i / 10,
            "members": 10_000 * (i + 1),
            "genres": [{"name": "Action"}, {"name": "Adventure"}],
            "studios": [{"name": f"Studio {i}"}],
        }
        for i in range(1, n + 1)
    ]}


def test_source_is_evidence_source():
    assert isinstance(AnimeMetadataSource(), EvidenceSource)


def test_fetch_maps_results_to_evidence():
    src = AnimeMetadataSource()
    fake = FakeJikan(_sample_payload(3))
    src._client = fake
    out = src.fetch(Query(text="naruto", limit=3))
    assert len(out) == 3
    for i, ev in enumerate(out, start=1):
        assert ev.source == "anime_metadata"
        assert ev.url == f"https://myanimelist.net/anime/{i}"
        assert ev.title == f"Title {i}"
        assert ev.metadata["mal_id"] == i
        assert ev.metadata["type"] == "TV"
        assert ev.metadata["episodes"] == 12 + i
        assert ev.metadata["genres"] == ["Action", "Adventure"]
        assert ev.metadata["studios"] == [f"Studio {i}"]
        assert ev.metadata["query"] == "naruto"
        # content is canonical sort_keys JSON of the raw item
        assert ev.content == json.dumps(_sample_payload(3)["data"][i - 1],
                                        ensure_ascii=False, sort_keys=True)


def test_fetch_limit_truncates_and_floor_is_one():
    src = AnimeMetadataSource()
    src._client = FakeJikan(_sample_payload(10))
    assert len(src.fetch(Query(text="q", limit=2))) == 2
    # max(1, limit): 0 and negative limits still return one row (current)
    assert len(src.fetch(Query(text="q", limit=0))) == 1
    assert len(src.fetch(Query(text="q", limit=-5))) == 1
    assert len(src.fetch(Query(text="q", limit=10))) == 10


def test_fetch_passes_search_type_and_page():
    src = AnimeMetadataSource()
    fake = FakeJikan({"data": []})
    src._client = fake
    src.fetch(Query(text="q", limit=1, extra={"search_type": "manga", "page": 3}))
    assert fake.calls == [("manga", "q", 3)]
    fake2 = FakeJikan({"data": []})
    src._client = fake2
    src.fetch(Query(text="q", limit=1))
    assert fake2.calls == [("anime", "q", None)]  # defaults


def test_fetch_empty_data_gives_empty_list():
    src = AnimeMetadataSource()
    src._client = FakeJikan({"data": []})
    assert src.fetch(Query(text="q")) == []
    src._client = FakeJikan({})
    assert src.fetch(Query(text="q")) == []


def test_fetch_search_failure_raises_provider_error():
    src = AnimeMetadataSource()
    src._client = FakeJikan(error=RuntimeError("503 upstream"))
    with pytest.raises(ProviderError, match="jikan search failed"):
        src.fetch(Query(text="q"))


def test_fetch_throttles_when_called_too_soon(monkeypatch):
    now = {"t": 100.0}
    slept = []
    monkeypatch.setattr(amod.time, "monotonic", lambda: now["t"])
    monkeypatch.setattr(amod.time, "sleep", slept.append)
    src = AnimeMetadataSource(min_interval=0.5)
    src._last_call = now["t"] - 0.1  # last call only 0.1s ago
    src._client = FakeJikan({"data": []})
    src.fetch(Query(text="q", limit=1))
    assert slept and slept[0] == pytest.approx(0.4)  # 0.5 - 0.1
    # and _last_call advanced
    assert src._last_call == 100.0


def test_fetch_no_throttle_when_enough_time_passed(monkeypatch):
    now = {"t": 100.0}
    slept = []
    monkeypatch.setattr(amod.time, "monotonic", lambda: now["t"])
    monkeypatch.setattr(amod.time, "sleep", slept.append)
    src = AnimeMetadataSource(min_interval=0.5)
    src._last_call = 50.0
    src._client = FakeJikan({"data": []})
    src.fetch(Query(text="q", limit=1))
    assert slept == []


def test_source_via_registry(reg):
    src = reg.create("source", "anime_metadata")
    assert isinstance(src, AnimeMetadataSource)
    assert isinstance(src, EvidenceSource)
