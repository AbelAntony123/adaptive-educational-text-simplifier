"""Dependency-free readability and word-count metrics."""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"\b[\w]+(?:['’][\w]+)?\b", re.UNICODE)
_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)")


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def _syllables(word: str) -> int:
    normalized = re.sub(r"[^a-z]", "", word.lower())
    if not normalized:
        return 0
    groups = re.findall(r"[aeiouy]+", normalized)
    count = len(groups)
    if normalized.endswith("e") and count > 1 and not normalized.endswith(("le", "ye")):
        count -= 1
    return max(1, count)


def readability_score(text: str) -> float | None:
    """Flesch Reading Ease (0–100-ish; higher means easier to read)."""
    words = _WORD_RE.findall(text)
    sentences = [s for s in _SENTENCE_RE.findall(text) if _WORD_RE.search(s)]
    if not words or not sentences:
        return None
    syllables = sum(_syllables(w) for w in words)
    score = 206.835 - 1.015 * (len(words) / len(sentences)) - 84.6 * (syllables / len(words))
    return round(score, 2)


def average_sentence_length(text: str) -> float | None:
    """Average number of words per sentence, or None if the text has no sentences."""
    sentences = [s for s in _SENTENCE_RE.findall(text) if _WORD_RE.search(s)]
    if not sentences:
        return None
    return word_count(text) / len(sentences)


def calculate_metrics(original_text: str, simplified_text: str, similarity_fn=None) -> dict:
    metrics = {
        "readability_score": readability_score(simplified_text),
        "semantic_similarity": None,
        "word_count_original": word_count(original_text),
        "word_count_simplified": word_count(simplified_text),
    }
    if similarity_fn is not None:
        metrics["semantic_similarity"] = similarity_fn(original_text, simplified_text)
    return metrics
