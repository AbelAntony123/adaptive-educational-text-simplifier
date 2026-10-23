"""Deterministic preservation checks plus a second-model factuality review."""

from __future__ import annotations

import re

from .llm_client import verify_text

_NUMBER_RE = re.compile(r"(?<!\w)[+-]?\d+(?:[.,]\d+)*(?:%|°[CF])?(?!\w)")
_CAPITALIZED_RE = re.compile(r"\b[A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*)*")
_TECHNICAL_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:[-/][A-Za-z0-9]+)+\b")


def _missing_terms(original: str, simplified: str) -> list[str]:
    targets = set(_NUMBER_RE.findall(original)) | set(_TECHNICAL_RE.findall(original))
    # Sentence-initial capitalization alone is not treated as a named entity.
    for sentence in re.split(r"(?<=[.!?])\s+", original):
        tokens = _CAPITALIZED_RE.findall(sentence)
        if tokens:
            targets.update(phrase for phrase in tokens[1:] if phrase.casefold() not in {"the", "a", "an"})
    folded = simplified.casefold()
    return sorted(term for term in targets if term.casefold() not in folded)


def verify(original: str, simplified: str, verifier=verify_text) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    missing = _missing_terms(original, simplified)
    details.append(
        {
            "check": "Numbers, names, and technical terms",
            "status": "FAIL" if missing else "PASS",
            "explanation": (
                "Missing source terms: " + ", ".join(missing[:12])
                if missing
                else "Detected numbers, capitalized names, and hyphenated technical terms are present."
            ),
        }
    )
    original_words = max(1, len(re.findall(r"\b\w+\b", original)))
    simplified_words = len(re.findall(r"\b\w+\b", simplified))
    length_bad = simplified_words == 0 or simplified_words > original_words * 2.5 + 20
    details.append(
        {
            "check": "Output length sanity",
            "status": "FAIL" if length_bad else "PASS",
            "explanation": "Output is empty or exceeds the length sanity bound." if length_bad else "Output length is within the sanity bound.",
        }
    )
    try:
        result = verifier(original, simplified)
        unsupported = result.get("unsupported_claims", [])
        omissions = result.get("omissions", [])
        supported = result["supported"] is True and not unsupported
        meaning = result["meaning_preserved"] is True and not omissions
        details.append(
            {
                "check": "Model factuality review",
                "status": "PASS" if supported else "FAIL",
                "explanation": str(result.get("explanation") or ("No unsupported claims reported." if supported else "Possible unsupported claims: " + "; ".join(map(str, unsupported[:5]))))[:500],
            }
        )
        details.append(
            {
                "check": "Meaning preservation review",
                "status": "PASS" if meaning else "FAIL",
                "explanation": "Important meaning and qualifications appear preserved." if meaning else "Potential omissions: " + "; ".join(map(str, omissions[:5]))[:450],
            }
        )
    except Exception as exc:
        code = getattr(exc, "code", "VERIFICATION_UNAVAILABLE")
        message = getattr(exc, "public_message", "The model review could not run.")
        details.append({"check": "Model factuality review", "status": "NOT RUN", "explanation": f"{code}: {message}"})
        details.append({"check": "Meaning preservation review", "status": "NOT RUN", "explanation": f"{code}: {message}"})
    return details
