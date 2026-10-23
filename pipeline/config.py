"""Configuration read from environment variables only."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    embedding_model: str
    max_attempts: int
    max_input_chars: int
    timeout_seconds: float


def _positive_int(name: str, default: int, *, maximum: int | None = None) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    if value < 1 or (maximum is not None and value > maximum):
        return default
    return value


def _positive_float(name: str, default: float, *, maximum: float | None = None) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    if value <= 0 or (maximum is not None and value > maximum):
        return default
    return value


def get_settings() -> Settings:
    return Settings(
        api_key=os.environ.get("GEMINI_API_KEY", "").strip(),
        model=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash",
        embedding_model=os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2-preview").strip()
        or "gemini-embedding-2-preview",
        max_attempts=_positive_int("SIMPLIFIER_MAX_ATTEMPTS", 3, maximum=5),
        max_input_chars=_positive_int("SIMPLIFIER_MAX_INPUT_CHARS", 20_000),
        # Worst case 5 generations, 3 verification requests and 2 embedding requests
        # must fit inside the UI's 180-second total timeout.
        timeout_seconds=_positive_float("GEMINI_TIMEOUT_SECONDS", 15.0, maximum=15.0),
    )
