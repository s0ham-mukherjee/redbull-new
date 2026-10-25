"""Text processing: multilingual sentiment & Indic-script normalization.

Upstream clones: huggingface/transformers (Apache-2.0),
anoopkunchukuttan/indic_nlp_library (MIT).

Exposed capabilities:
- ``sentiment`` / ``transformer`` - multilingual sentiment scoring (Feature 24).
- ``text`` / ``indic`` - script normalization/tokenization for Hindi, Tamil,
  Telugu, Bengali etc. (Feature 32).
"""

from __future__ import annotations

from typing import Any, Sequence

from engine_api import provider

from ._bootstrap import ProviderError, ensure_paths


class TransformerSentiment:
    """SentimentAnalyzer over a HuggingFace pipeline (default: XLM-R multilingual)."""

    def __init__(self, model: str = "cardiffnlp/twitter-xlm-roberta-base-sentiment",
                 device: int | str | None = None) -> None:
        self._model = model
        self._device = device
        self._pipeline: Any = None

    @property
    def _pipe(self) -> Any:
        if self._pipeline is None:
            ensure_paths("transformers")
            from transformers import pipeline  # lazy upstream import

            kwargs: dict[str, Any] = {"model": self._model}
            if self._device is not None:
                kwargs["device"] = self._device
            self._pipeline = pipeline("sentiment-analysis", **kwargs)
        return self._pipeline

    def analyze(self, texts: Sequence[str]) -> list[float]:
        """Return scores in [-1, 1] (negative -> -score, neutral -> 0)."""
        if not texts:
            return []
        try:
            raw = self._pipe(list(texts), truncation=True, max_length=512)
        except Exception as exc:
            raise ProviderError(f"sentiment pipeline failed: {exc}") from exc
        scores: list[float] = []
        for entry in raw:
            label = str(entry.get("label", "")).upper()
            value = float(entry.get("score", 0.0))
            if "NEG" in label:
                scores.append(-value)
            elif "NEU" in label:
                scores.append(0.0)
            else:
                scores.append(value)
        return scores


class IndicTextProcessor:
    """TextProcessor: normalization + tokenization for Indian languages.

    ``normalize_text`` additionally strips ZWJ/ZWNJ, unifies Devanagari
    matras and converts shared Indic digits, keeping code-switched
    (Hinglish) Latin segments untouched.
    """

    def __init__(self, default_language: str = "hi") -> None:
        ensure_paths("indic_nlp_library")
        self._default_language = default_language
        self._normalizer: Any = None

    @property
    def normalizer(self) -> Any:
        if self._normalizer is None:
            from indicnlp.normalize.indic_normalize import IndicNormalizerFactory

            self._normalizer = IndicNormalizerFactory()
        return self._normalizer

    def detect_language(self, text: str) -> str | None:
        """Detect Indic language from Unicode script ranges; None if Latin-only."""
        from indicnlp.langinfo import SCRIPT_RANGES  # lazy upstream import

        counts: dict[str, int] = {}
        for char in text:
            if char.isspace() or char.isascii():
                continue
            for lang, (start, end) in SCRIPT_RANGES.items():
                if start <= ord(char) <= end:
                    counts[lang] = counts.get(lang, 0) + 1
                    break
        if not counts:
            return None
        return max(counts, key=counts.get)  # type: ignore[arg-type]

    def normalize_text(self, text: str, language: str | None = None) -> str:
        lang = language or self.detect_language(text) or self._default_language
        try:
            normalizer = self.normalizer.get_normalizer(lang)
            return normalizer.normalize(text)
        except Exception as exc:
            raise ProviderError(f"indic normalization failed ({lang}): {exc}") from exc

    def tokenize(self, text: str, language: str | None = None) -> list[str]:
        from indicnlp.tokenize.indic_tokenize import trivial_tokenize

        lang = language or self.detect_language(text) or self._default_language
        return trivial_tokenize(text, lang=lang)


@provider("sentiment", "transformer")
def _sentiment_factory(**config: Any) -> TransformerSentiment:
    return TransformerSentiment(**config)


@provider("text", "indic")
def _text_factory(**config: Any) -> IndicTextProcessor:
    return IndicTextProcessor(**config)


__all__ = ["TransformerSentiment", "IndicTextProcessor"]
