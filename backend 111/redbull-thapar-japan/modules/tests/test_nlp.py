"""TransformerSentiment with a fake pipeline + IndicTextProcessor offline."""

from __future__ import annotations

import pytest

from engine_api.protocols import SentimentAnalyzer, TextProcessor
from providers._bootstrap import ProviderError
from providers.nlp import IndicTextProcessor, TransformerSentiment


# ---------------------------------------------------------------------------
# TransformerSentiment
# ---------------------------------------------------------------------------


class FakePipeline:
    """Callable standing in for a HF sentiment pipeline."""

    def __init__(self, labels=None, scores=None, error=None):
        self.labels = labels or []
        self.scores = scores or []
        self.error = error
        self.calls = []

    def __call__(self, texts, **kwargs):
        self.calls.append((list(texts), kwargs))
        if self.error is not None:
            raise self.error
        return [{"label": self.labels[i % len(self.labels)],
                 "score": self.scores[i % len(self.scores)]}
                for i in range(len(texts))]


def test_analyze_negative_maps_to_negative_score():
    ts = TransformerSentiment()
    ts._pipeline = FakePipeline(labels=["NEGATIVE"], scores=[0.9])
    assert ts.analyze(["bad"]) == [-0.9]


def test_analyze_neutral_maps_to_zero():
    ts = TransformerSentiment()
    ts._pipeline = FakePipeline(labels=["NEUTRAL"], scores=[0.99])
    assert ts.analyze(["meh"]) == [0.0]


def test_analyze_positive_maps_to_positive_score():
    ts = TransformerSentiment()
    ts._pipeline = FakePipeline(labels=["POSITIVE"], scores=[0.8])
    assert ts.analyze(["great"]) == [0.8]


def test_analyze_unknown_label_maps_to_positive_score():
    # CURRENT: the final `else` branch scores any unrecognized label as +score
    ts = TransformerSentiment()
    ts._pipeline = FakePipeline(labels=["LABEL_7"], scores=[0.5])
    assert ts.analyze(["x"]) == [0.5]


@pytest.mark.parametrize("label", ["negative", "Negative", "NEG", "1 star NEGATIVE"])
def test_analyze_label_matching_is_case_insensitive_and_substring(label):
    ts = TransformerSentiment()
    ts._pipeline = FakePipeline(labels=[label], scores=[0.7])
    assert ts.analyze(["x"]) == [-0.7]


def test_analyze_mixed_labels_map_per_entry():
    ts = TransformerSentiment()
    fake = FakePipeline(labels=["NEGATIVE", "NEUTRAL", "POSITIVE"],
                        scores=[0.9, 0.6, 0.4])
    ts._pipeline = fake
    assert ts.analyze(["a", "b", "c"]) == [-0.9, 0.0, 0.4]


def test_analyze_empty_texts_returns_empty_without_calling_pipeline():
    ts = TransformerSentiment()
    ts._pipeline = FakePipeline(error=AssertionError("must not be called"))
    assert ts.analyze([]) == []


def test_analyze_pipeline_failure_raises_provider_error():
    ts = TransformerSentiment()
    ts._pipeline = FakePipeline(error=RuntimeError("OOM"))
    with pytest.raises(ProviderError, match="sentiment pipeline failed"):
        ts.analyze(["x"])


def test_analyze_truncation_kwargs_forwarded():
    ts = TransformerSentiment()
    fake = FakePipeline(labels=["POSITIVE"], scores=[1.0])
    ts._pipeline = fake
    ts.analyze(["hello", "world"])
    assert fake.calls == [(["hello", "world"],
                           {"truncation": True, "max_length": 512})]


def test_analyze_missing_keys_default_to_zero_score_and_empty_label():
    ts = TransformerSentiment()
    ts._pipeline = lambda texts, **kw: [{}, {}]  # no label/score keys
    assert ts.analyze(["a", "b"]) == [0.0, 0.0]  # else branch with score 0.0


def test_sentiment_satisfies_protocol():
    assert isinstance(TransformerSentiment(), SentimentAnalyzer)


def test_sentiment_via_registry(reg):
    ts = reg.create("sentiment", "transformer")
    assert isinstance(ts, SentimentAnalyzer)


# ---------------------------------------------------------------------------
# IndicTextProcessor
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def proc():
    return IndicTextProcessor()


DEVANAGARI = "नमस्ते दुनिया"
TAMIL = "வணக்கம் உலகம்"
BENGALI = "নমস্কার বিশ্ব"


def test_detect_devanagari_maps_to_hi(proc):
    assert proc.detect_language(DEVANAGARI) == "hi"


def test_detect_tamil(proc):
    assert proc.detect_language(TAMIL) == "ta"


def test_detect_bengali(proc):
    assert proc.detect_language(BENGALI) == "bn"


def test_detect_latin_only_returns_none(proc):
    assert proc.detect_language("plain english text 123") is None
    assert proc.detect_language("") is None
    assert proc.detect_language("   \t\n") is None


def test_detect_ascii_punctuation_and_digits_skipped(proc):
    assert proc.detect_language("!?.,;:'\"[]{}()<>-_=+@#$%^&* 0123456789") is None


def test_detect_mixed_majority_script_wins(proc):
    mixed = DEVANAGARI + " " + TAMIL + " " + TAMIL
    assert proc.detect_language(mixed) == "ta"
    mixed2 = DEVANAGARI + " " + DEVANAGARI + " " + TAMIL
    assert proc.detect_language(mixed2) == "hi"


def test_detect_hinglish_latin_with_one_devanagari_char(proc):
    assert proc.detect_language("kya scene hai क") == "hi"


def test_detect_language_matches_script_ranges_reference():
    # self-consistency against the upstream SCRIPT_RANGES table
    from providers._bootstrap import ensure_paths
    ensure_paths("indic_nlp_library")
    from indicnlp.langinfo import SCRIPT_RANGES

    text = "कখगघङ"
    counts = {}
    for ch in text:
        for lang, (start, end) in SCRIPT_RANGES.items():
            if start <= ord(ch) <= end:
                counts[lang] = counts.get(lang, 0) + 1
                break
    expected = max(counts, key=counts.get)
    assert IndicTextProcessor().detect_language(text) == expected


def test_normalize_text_with_explicit_language(proc):
    out = proc.normalize_text(DEVANAGARI, language="hi")
    assert isinstance(out, str) and out  # must not blank the string


def test_normalize_text_failure_raises_provider_error_mentioning_language():
    proc = IndicTextProcessor()

    class BadFactory:
        def get_normalizer(self, lang):
            raise RuntimeError("unsupported language")

    proc._normalizer = BadFactory()
    with pytest.raises(ProviderError) as exc:
        proc.normalize_text("some text", language="zz")
    assert "zz" in str(exc.value)


def test_normalize_text_detect_fallback_default_language():
    # Latin-only text detects None -> default_language 'hi' is used, no raise
    proc = IndicTextProcessor(default_language="hi")
    out = proc.normalize_text("hello world")
    assert isinstance(out, str)


def test_normalize_text_detected_language_used():
    proc = IndicTextProcessor(default_language="zz")  # wrong default on purpose
    # Devanagari detection wins before the (bad) default kicks in
    out = proc.normalize_text(DEVANAGARI)
    assert isinstance(out, str) and out


def test_tokenize_splits_words(proc):
    toks = proc.tokenize("नमस्ते दुनिया", language="hi")
    assert isinstance(toks, list) and toks
    toks_en = proc.tokenize("hello world", language="en")
    assert "hello" in toks_en and "world" in toks_en


def test_tokenize_default_language_fallback(proc):
    assert proc.tokenize("two words")  # detect None -> 'hi' -> still tokenizes


def test_text_processor_satisfies_protocol(proc):
    assert isinstance(proc, TextProcessor)


def test_text_processor_via_registry(reg):
    p = reg.create("text", "indic")
    assert isinstance(p, TextProcessor)
