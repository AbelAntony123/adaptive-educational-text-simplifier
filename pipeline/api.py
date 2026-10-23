"""Public backend entry point matching the Streamlit adapter contract."""

from __future__ import annotations

import time

from .config import get_settings
from .evaluation import calculate_metrics
from .llm_client import LLMError, generate_text, semantic_similarity
from .prompts import PROMPT_VERSION
from .verification import verify

LEVELS = ("Beginner", "Intermediate", "Advanced")
STATUSES = ("PASS", "FAIL", "NOT RUN")

# Seconds to wait before retrying a temporary provider error (for example HTTP 503).
RETRY_PAUSES = (1.0, 2.0, 2.0, 2.0)
# Temporary errors get their own small retry budget, so a busy provider does not
# use up the attempts reserved for fixing verification failures.
MAX_TRANSIENT_RETRIES = 2
# RATE_LIMIT is deliberately not retried: a per-minute quota needs a much longer wait
# than the short pauses here, and quick retries only use up more of the quota.
TRANSIENT_CODES = {"API_TIMEOUT", "API_ERROR"}
_sleep = time.sleep


def _error(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def _result(original: str, level: str, simplified: str = "", status: str = "NOT RUN", details=None, metrics=None, attempts=0, errors=None) -> dict:
    return {
        "original_text": original,
        "simplified_text": simplified,
        "level": level,
        "verification_status": status,
        "verification_details": details or [],
        "metrics": metrics or {
            "readability_score": None,
            "semantic_similarity": None,
            "word_count_original": None,
            "word_count_simplified": None,
        },
        "attempts": attempts,
        "errors": errors or [],
    }


def _overall_status(details: list[dict]) -> str:
    if any(item["status"] == "FAIL" for item in details):
        return "FAIL"
    if details and all(item["status"] == "PASS" for item in details):
        return "PASS"
    return "NOT RUN"


def _feedback(details: list[dict]) -> str:
    return "; ".join(f"{d['check']}: {d['explanation']}" for d in details if d["status"] == "FAIL")[:1500]


def simplify_text(original_text: str, level: str) -> dict:
    """Simplify text and return a complete result dictionary; expected errors do not escape."""
    text = original_text if isinstance(original_text, str) else ""
    level_value = level if isinstance(level, str) else ""
    settings = get_settings()
    if not isinstance(original_text, str) or not original_text.strip():
        return _result(text, level_value, errors=[_error("INVALID_INPUT", "Input text must be a non-empty string.")])
    if level_value not in LEVELS:
        return _result(text, level_value, errors=[_error("INVALID_LEVEL", "Level must be Beginner, Intermediate, or Advanced.")])
    if len(text) > settings.max_input_chars:
        return _result(text, level_value, errors=[_error("INPUT_TOO_LONG", f"Input exceeds the {settings.max_input_chars}-character limit.")])
    if not settings.api_key:
        return _result(text, level_value, errors=[_error("MISSING_API_KEY", "Set GEMINI_API_KEY in the environment to use the Gemini backend.")])

    best_text = ""
    best_details: list[dict] = []
    attempts = 0  # every generation request started; this is what the UI shows
    generated = 0  # requests that returned a response; limited by max_attempts
    transient_retries = 0
    errors: list[dict] = []
    retry_feedback = ""

    while generated < settings.max_attempts:
        attempts += 1
        try:
            candidate = generate_text(text, level_value, retry_feedback).strip()
        except LLMError as exc:
            errors.append(_error(exc.code, exc.public_message))
            # Retrying transient provider errors can recover from a brief interruption.
            if exc.code in TRANSIENT_CODES and transient_retries < MAX_TRANSIENT_RETRIES:
                _sleep(RETRY_PAUSES[min(transient_retries, len(RETRY_PAUSES) - 1)])
                transient_retries += 1
                continue
            break
        generated += 1
        if not candidate or candidate == text.strip():
            retry_feedback = "The previous output was empty or unchanged. Produce a genuine rewrite while preserving meaning."
            errors.append(_error("MODEL_OUTPUT_INVALID", "Gemini returned empty or unchanged text."))
            continue

        best_text = candidate
        best_details = verify(text, candidate)
        status = _overall_status(best_details)
        if status == "PASS":
            break
        if status == "NOT RUN":
            explanation = next(
                (item["explanation"] for item in best_details if item["status"] == "NOT RUN"),
                "The simplification was produced, but the factuality review did not complete.",
            )
            known_codes = {
                "API_TIMEOUT", "RATE_LIMIT", "API_ERROR", "API_AUTH_ERROR",
                "MISSING_API_KEY", "MODEL_OUTPUT_INVALID", "DEPENDENCY_MISSING",
                "METRIC_UNAVAILABLE",
            }
            code, separator, message = explanation.partition(": ")
            if not separator or code not in known_codes:
                code, message = "VERIFICATION_UNAVAILABLE", "The factuality review did not complete."
            errors.append(_error(code, message))
            break
        retry_feedback = _feedback(best_details)

    if not best_text:
        if not errors:
            errors.append(_error("MODEL_OUTPUT_INVALID", "No usable simplification was produced."))
        return _result(text, level_value, attempts=attempts, errors=errors)

    status = _overall_status(best_details)
    if status == "FAIL":
        errors.append(_error("VERIFICATION_FAILED", "The best generated result did not pass every verification check."))
    try:
        metrics = calculate_metrics(text, best_text, semantic_similarity)
    except LLMError as exc:
        metrics = calculate_metrics(text, best_text)
        errors.append(_error(exc.code, exc.public_message))
    except Exception:
        metrics = calculate_metrics(text, best_text)
        errors.append(_error("METRIC_UNAVAILABLE", "Semantic similarity could not be computed."))
    # Reproducibility metadata stays in logs, not in the UI contract response.
    import logging

    logging.getLogger(__name__).info("result model=%s prompt_version=%s attempts=%d", settings.model, PROMPT_VERSION, attempts)
    return _result(text, level_value, best_text, status, best_details, metrics, attempts, errors)
