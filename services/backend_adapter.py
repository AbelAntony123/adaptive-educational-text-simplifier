"""The only module that talks to the simplification backend.

The UI calls ``simplify()`` and always gets back a dictionary with the same
shape, whether the data is mock or real, and whether the call worked or not.
This keeps the UI independent of the LLM code.

The expected backend contract is a PROPOSAL until the backend team confirms it:

    simplify_text(original_text: str, level: str) -> dict

Whatever the backend returns is checked here. Missing or invalid values become
``None`` (shown as N/A) or ``NOT RUN``. Nothing is invented and nothing is
silently turned into zero.
"""

from __future__ import annotations

import copy
import importlib
import math
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, Callable, MutableMapping

from services import mock_data

LEVELS = ("Beginner", "Intermediate", "Advanced")
STATUSES = ("PASS", "FAIL", "NOT RUN")

SOURCE_MOCK = "mock"
SOURCE_BACKEND = "backend"
SOURCE_DESCRIPTIONS = {
    SOURCE_MOCK: "MOCK DATA - example output, not produced by an AI model and not a research finding",
    SOURCE_BACKEND: "Real backend output",
}

MAX_INPUT_CHARS = 20_000  # UI-side safety limit, not a confirmed backend limit
BACKEND_TIMEOUT_SECONDS = 180  # backend worst case is about 150 s (see docs/BACKEND_CONTRACT.md)
BACKEND_MODULE_ENV = "SIMPLIFIER_BACKEND_MODULE"
BACKEND_FUNCTION_NAME = "simplify_text"

# Saved results are only reused while these settings stay the same.
CACHE_ENV_NAMES = (BACKEND_MODULE_ENV, "GEMINI_MODEL", "GEMINI_EMBEDDING_MODEL", "SIMPLIFIER_MAX_ATTEMPTS")
CACHE_LIMIT = 50

METRIC_KEYS = (
    "readability_score",
    "semantic_similarity",
    "word_count_original",
    "word_count_simplified",
)
_INTEGER_METRICS = ("word_count_original", "word_count_simplified")


def validate_input(text: Any, level: Any) -> list[str]:
    """Return a list of user-friendly problems (empty list means the input is fine)."""
    problems: list[str] = []
    if not isinstance(text, str) or not text.strip():
        problems.append("Please enter or upload some text before simplifying.")
    elif len(text) > MAX_INPUT_CHARS:
        problems.append(
            f"The text is {len(text):,} characters long. Please shorten it to {MAX_INPUT_CHARS:,} characters or fewer."
        )
    if level not in LEVELS:
        problems.append(f"Please choose a difficulty level: {', '.join(LEVELS)}.")
    return problems


def make_error_result(original_text: str, level: str, source: str, code: str, message: str) -> dict:
    """A result with no simplified text, nothing verified and every metric unavailable."""
    return {
        "original_text": original_text if isinstance(original_text, str) else "",
        "simplified_text": "",
        "level": level,
        "verification_status": "NOT RUN",
        "verification_details": [],
        "metrics": {key: None for key in METRIC_KEYS},
        "attempts": None,
        "errors": [{"code": code, "message": message}],
        "source": source,
        "warnings": [],
        "cached": False,
        "fallback_notice": None,
    }


def _clean_number(value: Any, integer: bool) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if integer:
        if value < 0 or int(value) != value:
            return None
        return int(value)
    return float(value)


def _normalize_details(raw_details: Any, warnings: list[str]) -> list[dict]:
    if raw_details is None:
        return []
    if not isinstance(raw_details, list):
        warnings.append("Verification details were not a list, so they were ignored.")
        return []
    details: list[dict] = []
    for item in raw_details:
        if isinstance(item, dict):
            status = item.get("status")
            if status not in STATUSES:
                warnings.append(f"A verification check had an unrecognised result ({status!r}); it is shown as NOT RUN.")
                status = "NOT RUN"
            details.append(
                {
                    "check": str(item.get("check") or "Unnamed check"),
                    "status": status,
                    "explanation": str(item.get("explanation") or "No explanation provided."),
                }
            )
        else:
            warnings.append(
                "A verification detail was plain text without a PASS/FAIL result, so it is shown as NOT RUN."
            )
            details.append({"check": "Unspecified check", "status": "NOT RUN", "explanation": str(item)})
    return details


def _normalize_errors(raw_errors: Any, warnings: list[str]) -> list[dict]:
    if raw_errors is None:
        return []
    if not isinstance(raw_errors, list):
        warnings.append("The error list was not in the expected format.")
        raw_errors = [raw_errors] if raw_errors else []
    errors: list[dict] = []
    for item in raw_errors:
        if isinstance(item, dict):
            errors.append(
                {
                    "code": str(item.get("code") or "UNKNOWN"),
                    "message": str(item.get("message") or "No message provided."),
                }
            )
        else:
            errors.append({"code": "UNSPECIFIED", "message": str(item)})
    return errors


def normalize_response(raw: Any, original_text: str, level: str, source: str) -> dict:
    """Check a raw backend response and return a safe, complete result dictionary."""
    if not isinstance(raw, dict):
        return make_error_result(
            original_text,
            level,
            source,
            "INVALID_RESPONSE",
            f"The backend returned {type(raw).__name__} instead of a dictionary.",
        )

    warnings: list[str] = []

    original = raw.get("original_text")
    if not isinstance(original, str):
        original = original_text

    simplified = raw.get("simplified_text")
    if not isinstance(simplified, str):
        if simplified is not None:
            warnings.append("The simplified text was not text, so it was ignored.")
        simplified = ""

    result_level = raw.get("level")
    if result_level not in LEVELS:
        warnings.append("The response did not contain a valid level; the requested level is shown.")
        result_level = level
    elif result_level != level:
        warnings.append(f"You asked for {level}, but the backend reports {result_level}.")

    details = _normalize_details(raw.get("verification_details"), warnings)
    errors = _normalize_errors(raw.get("errors"), warnings)

    status = raw.get("verification_status")
    if status not in STATUSES:
        warnings.append(f"The verification status was missing or unrecognised ({status!r}); it is shown as NOT RUN.")
        status = "NOT RUN"
    if any(d["status"] == "FAIL" for d in details) and status != "FAIL":
        warnings.append("At least one check failed, so the overall status is shown as FAIL.")
        status = "FAIL"
    if status == "PASS":
        if not simplified.strip():
            warnings.append("There is no simplified text to verify, so the status is shown as NOT RUN.")
            status = "NOT RUN"
        elif details and not any(d["status"] == "PASS" for d in details):
            warnings.append("No individual check reported PASS, so the overall status is shown as NOT RUN.")
            status = "NOT RUN"
        elif not details:
            warnings.append("The backend reported PASS but gave no details about which checks ran.")

    raw_metrics = raw.get("metrics")
    if raw_metrics is not None and not isinstance(raw_metrics, dict):
        warnings.append("Metrics were not in the expected format, so they are shown as N/A.")
        raw_metrics = {}
    raw_metrics = raw_metrics or {}
    metrics: dict[str, int | float | None] = {}
    for key in METRIC_KEYS:
        value = raw_metrics.get(key)
        cleaned = _clean_number(value, integer=key in _INTEGER_METRICS)
        if value is not None and cleaned is None:
            warnings.append(f"The value for {key} was not a valid number, so it is shown as N/A.")
        metrics[key] = cleaned

    attempts = raw.get("attempts")
    if attempts is not None and _clean_number(attempts, integer=True) is None:
        warnings.append("The number of attempts was not a valid whole number, so it is shown as N/A.")
    attempts = _clean_number(attempts, integer=True)

    return {
        "original_text": original,
        "simplified_text": simplified,
        "level": result_level,
        "verification_status": status,
        "verification_details": details,
        "metrics": metrics,
        "attempts": attempts,
        "errors": errors,
        "source": source,
        "warnings": warnings,
        "cached": False,
        "fallback_notice": None,
    }


def _load_real_backend() -> tuple[Callable[[str, str], Any] | None, str | None]:
    """Find the teammate's simplify_text function. Returns (function, problem)."""
    module_name = os.environ.get(BACKEND_MODULE_ENV, "").strip()
    if not module_name:
        return None, (
            "The real backend is not connected yet. When it is ready, set the environment variable "
            f"{BACKEND_MODULE_ENV} to the module that contains {BACKEND_FUNCTION_NAME}, or switch to mock data."
        )
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        return None, f"The backend module '{module_name}' could not be imported ({exc})."
    function = getattr(module, BACKEND_FUNCTION_NAME, None)
    if not callable(function):
        return None, f"The backend module '{module_name}' has no function called {BACKEND_FUNCTION_NAME}."
    return function, None


def _call_with_timeout(function: Callable[[str, str], Any], text: str, level: str, timeout: float) -> Any:
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        return executor.submit(function, text, level).result(timeout=timeout)
    finally:
        # Do not wait for a stuck call; the user gets the timeout message at once.
        executor.shutdown(wait=False)


def _cache_key(text: str, level: str) -> tuple:
    """Same text, level and backend settings give the same key, so a repeat click can reuse the result."""
    return (text.strip(), level, tuple(os.environ.get(name, "") for name in CACHE_ENV_NAMES))


def _is_cacheable(result: dict) -> bool:
    """Only a clean, verified real result is saved. Errors, FAIL and NOT RUN results are always run again."""
    return (
        result["source"] == SOURCE_BACKEND
        and not result["errors"]
        and result["verification_status"] == "PASS"
        and bool(result["simplified_text"].strip())
    )


def _quota_exhausted(result: dict) -> bool:
    """True when the quota stopped the run before any simplified text existed."""
    return any(error["code"] == "RATE_LIMIT" for error in result["errors"]) and not result["simplified_text"].strip()


def simplify(
    text: str,
    level: str,
    mode: str = SOURCE_MOCK,
    scenario: str = "success",
    timeout: float = BACKEND_TIMEOUT_SECONDS,
    cache: MutableMapping | None = None,
    fallback_to_mock: bool = False,
) -> dict:
    """Run one simplification. Never raises; problems are reported in ``errors``.

    ``cache`` is a dict kept by the caller (the UI keeps one per session). A verified real result for the
    same text and level is reused instead of calling the backend again.
    ``fallback_to_mock`` shows clearly labelled demo data when the quota stopped a real run before it
    produced any text. Real text that already exists is never replaced.
    """
    source = SOURCE_BACKEND if mode == SOURCE_BACKEND else SOURCE_MOCK
    key = _cache_key(text, level) if cache is not None and source == SOURCE_BACKEND and isinstance(text, str) else None

    if key is not None and key in cache:
        reused = copy.deepcopy(cache[key])
        reused["cached"] = True
        reused["warnings"] = list(reused["warnings"]) + [
            "Reused a saved result from earlier in this session. No new Gemini requests were made."
        ]
        return reused

    result = _run_once(text, level, source, scenario, timeout)

    if key is not None and _is_cacheable(result):
        cache[key] = copy.deepcopy(result)
        while len(cache) > CACHE_LIMIT:
            cache.pop(next(iter(cache)))  # drop the oldest saved result

    if fallback_to_mock and source == SOURCE_BACKEND and _quota_exhausted(result):
        reason = next(error["message"] for error in result["errors"] if error["code"] == "RATE_LIMIT")
        demo = _run_once(text, level, SOURCE_MOCK, "success", timeout)
        demo["fallback_notice"] = (
            f"Gemini's quota ran out. {reason} These are demo results, not real model output."
        )
        return demo
    return result


def _run_once(text: str, level: str, source: str, scenario: str, timeout: float) -> dict:
    problems = validate_input(text, level)
    if problems:
        return make_error_result(text, level, source, "INVALID_INPUT", " ".join(problems))

    if source == SOURCE_MOCK:

        def function(original: str, chosen_level: str) -> Any:
            return mock_data.mock_simplify_text(original, chosen_level, scenario)

    else:
        function, problem = _load_real_backend()
        if function is None:
            return make_error_result(text, level, source, "BACKEND_UNAVAILABLE", problem or "Backend unavailable.")

    try:
        raw = _call_with_timeout(function, text, level, timeout)
    except FutureTimeout:
        return make_error_result(
            text, level, source, "BACKEND_TIMEOUT", f"The backend did not answer within {timeout:g} seconds."
        )
    except Exception as exc:  # the UI must never crash because of the backend
        return make_error_result(
            text, level, source, "BACKEND_EXCEPTION", f"{type(exc).__name__}: {str(exc)[:300]}"
        )
    return normalize_response(raw, text, level, source)
