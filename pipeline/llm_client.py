"""The only module that communicates with Google's Gemini API."""

from __future__ import annotations

import json
import logging
from typing import Any

from .config import get_settings
from .prompts import PROMPT_VERSION, simplification_prompt, verification_prompt

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Provider failure with a stable, safe public error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.public_message = message


def _client():
    settings = get_settings()
    if not settings.api_key:
        raise LLMError("MISSING_API_KEY", "Set GEMINI_API_KEY in the environment to use the Gemini backend.")
    try:
        from google import genai
        from google.genai import types

        return genai.Client(
            api_key=settings.api_key,
            # Keep retry counting in api.py, where ``attempts`` has a clear
            # definition for the UI contract.
            http_options=types.HttpOptions(
                timeout=int(settings.timeout_seconds * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
    except ImportError as exc:
        raise LLMError("DEPENDENCY_MISSING", "Install the backend dependency listed in pipeline/requirements.txt.") from exc
    except Exception as exc:
        raise _safe_provider_error(exc) from exc


def _safe_provider_error(exc: Exception) -> LLMError:
    name = type(exc).__name__.lower()
    status_code = getattr(exc, "code", None)
    # Only the exception type and HTTP status are logged, never the response text or key.
    logger.warning("Gemini request failed: type=%s status=%s", type(exc).__name__, status_code)
    if "timeout" in name or "deadline" in name or status_code in (408, 504):
        return LLMError("API_TIMEOUT", "Gemini did not respond before the configured timeout.")
    if "rate" in name or "resourceexhausted" in name or "quota" in name or status_code == 429:
        return LLMError("RATE_LIMIT", "Gemini rate or quota limit was reached. Wait about a minute before trying again.")
    if "unauth" in name or "permission" in name or status_code in (401, 403):
        return LLMError("API_AUTH_ERROR", "Gemini rejected the request. Check the API key and project access.")
    if status_code in (500, 502, 503):
        return LLMError("API_ERROR", f"Gemini is temporarily unavailable (HTTP {status_code}). Try again shortly.")
    return LLMError("API_ERROR", "The Gemini request failed. Check connectivity and API availability.")


def _response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if not isinstance(text, str) or not text.strip():
        raise LLMError("MODEL_OUTPUT_INVALID", "Gemini returned empty or malformed text.")
    return text.strip()


def generate_text(original_text: str, level: str, feedback: str = "") -> str:
    settings = get_settings()
    logger.info("LLM generation model=%s prompt_version=%s", settings.model, PROMPT_VERSION)
    client = _client()
    try:
        response = client.models.generate_content(
            model=settings.model,
            contents=simplification_prompt(original_text, level, feedback),
        )
        return _response_text(response)
    except LLMError:
        raise
    except Exception as exc:
        raise _safe_provider_error(exc) from exc


def verify_text(original_text: str, simplified_text: str) -> dict[str, Any]:
    settings = get_settings()
    logger.info("LLM verification model=%s prompt_version=%s", settings.model, PROMPT_VERSION)
    client = _client()
    try:
        from google.genai import types

        response = client.models.generate_content(
            model=settings.model,
            contents=verification_prompt(original_text, simplified_text),
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        raw = _response_text(response)
        parsed = json.loads(raw)
        required = {"supported", "meaning_preserved", "unsupported_claims", "omissions", "explanation"}
        if (
            not isinstance(parsed, dict)
            or set(parsed) != required
            or not isinstance(parsed.get("supported"), bool)
            or not isinstance(parsed.get("meaning_preserved"), bool)
            or not isinstance(parsed.get("unsupported_claims"), list)
            or not all(isinstance(item, str) for item in parsed["unsupported_claims"])
            or not isinstance(parsed.get("omissions"), list)
            or not all(isinstance(item, str) for item in parsed["omissions"])
            or not isinstance(parsed.get("explanation"), str)
        ):
            raise LLMError("MODEL_OUTPUT_INVALID", "Gemini returned malformed verification data.")
        return parsed
    except LLMError:
        raise
    except json.JSONDecodeError as exc:
        raise LLMError("MODEL_OUTPUT_INVALID", "Gemini returned malformed verification JSON.") from exc
    except Exception as exc:
        raise _safe_provider_error(exc) from exc


def _embed_one(client: Any, model: str, text: str) -> list[float]:
    """Embed one text per request.

    Some embedding models (for example gemini-embedding-2-preview) merge a list of
    texts into a single vector, so two texts must never share one request.
    """
    response = client.models.embed_content(model=model, contents=text)
    embeddings = list(response.embeddings or [])
    if len(embeddings) != 1:
        raise LLMError("METRIC_UNAVAILABLE", "Gemini returned unusable embeddings.")
    return list(embeddings[0].values)


def semantic_similarity(original_text: str, simplified_text: str) -> float:
    settings = get_settings()
    logger.info("LLM embedding model=%s prompt_version=%s", settings.embedding_model, PROMPT_VERSION)
    client = _client()
    try:
        vectors = [
            _embed_one(client, settings.embedding_model, original_text),
            _embed_one(client, settings.embedding_model, simplified_text),
        ]
        if not vectors[0] or len(vectors[0]) != len(vectors[1]):
            raise LLMError("METRIC_UNAVAILABLE", "Gemini returned unusable embeddings.")
        dot = sum(a * b for a, b in zip(vectors[0], vectors[1]))
        norm_a = sum(a * a for a in vectors[0]) ** 0.5
        norm_b = sum(b * b for b in vectors[1]) ** 0.5
        if not norm_a or not norm_b:
            raise LLMError("METRIC_UNAVAILABLE", "Gemini returned zero-length embeddings.")
        return max(0.0, min(1.0, (dot / (norm_a * norm_b) + 1.0) / 2.0))
    except LLMError:
        raise
    except Exception as exc:
        raise _safe_provider_error(exc) from exc
