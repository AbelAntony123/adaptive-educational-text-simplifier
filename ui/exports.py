"""Turn results into downloadable TXT and JSON text.

Only an explicit list of result fields is exported, so nothing else (such as
environment settings or keys) can end up in a file by accident.
"""

from __future__ import annotations

import json
from datetime import datetime

from services.backend_adapter import METRIC_KEYS, SOURCE_DESCRIPTIONS

EXPORT_FORMAT = "text-simplifier-result-v1"

_METRIC_LABELS = {
    "readability_score": "Readability score",
    "semantic_similarity": "Semantic similarity",
    "word_count_original": "Word count (original)",
    "word_count_simplified": "Word count (simplified)",
}


def _fmt(value) -> str:
    return "N/A" if value is None else str(value)


def _source_text(entry: dict) -> str:
    return SOURCE_DESCRIPTIONS.get(entry.get("source"), "Unknown source")


def export_filename(entry: dict, extension: str) -> str:
    try:
        stamp = datetime.fromisoformat(entry["created_at"]).strftime("%Y%m%d_%H%M%S")
    except (KeyError, ValueError, TypeError):
        stamp = "result"
    level = str(entry.get("level", "level")).lower()
    return f"simplification_{level}_{entry.get('source', 'unknown')}_{stamp}.{extension}"


def _export_dict(entry: dict) -> dict:
    return {
        "export_format": EXPORT_FORMAT,
        "source": entry.get("source"),
        "source_description": _source_text(entry),
        "created_at": entry.get("created_at"),
        "level": entry.get("level"),
        "verification_status": entry.get("verification_status"),
        "verification_details": entry.get("verification_details", []),
        "metrics": {key: entry.get("metrics", {}).get(key) for key in METRIC_KEYS},
        "attempts": entry.get("attempts"),
        "errors": entry.get("errors", []),
        "warnings": entry.get("warnings", []),
        "original_text": entry.get("original_text", ""),
        "simplified_text": entry.get("simplified_text", ""),
    }


def to_json(entry: dict) -> str:
    return json.dumps(_export_dict(entry), indent=2, ensure_ascii=False)


def history_to_json(entries: list[dict]) -> str:
    payload = {"export_format": EXPORT_FORMAT + "-history", "results": [_export_dict(e) for e in entries]}
    return json.dumps(payload, indent=2, ensure_ascii=False)


def to_txt(entry: dict) -> str:
    data = _export_dict(entry)
    lines = [
        "ADAPTIVE EDUCATIONAL TEXT SIMPLIFIER - RESULT",
        "=" * 46,
        f"Source: {data['source_description']}",
        f"Created: {_fmt(data['created_at'])}",
        f"Level: {_fmt(data['level'])}",
        f"Verification status: {_fmt(data['verification_status'])}",
        f"Attempts: {_fmt(data['attempts'])}",
        "",
        "ORIGINAL TEXT",
        "-" * 13,
        data["original_text"] or "(none)",
        "",
        "SIMPLIFIED TEXT",
        "-" * 15,
        data["simplified_text"] or "(none)",
        "",
        "VERIFICATION DETAILS",
        "-" * 20,
    ]
    if data["verification_details"]:
        for detail in data["verification_details"]:
            lines.append(f"[{detail['status']}] {detail['check']}: {detail['explanation']}")
    else:
        lines.append("No check details available.")
    lines += ["", "METRICS", "-" * 7]
    for key in METRIC_KEYS:
        lines.append(f"{_METRIC_LABELS[key]}: {_fmt(data['metrics'][key])}")
    lines += ["", "ERRORS", "-" * 6]
    if data["errors"]:
        for error in data["errors"]:
            lines.append(f"{error['code']}: {error['message']}")
    else:
        lines.append("None reported.")
    if data["warnings"]:
        lines += ["", "NOTES ABOUT THE RESPONSE", "-" * 24]
        lines += data["warnings"]
    return "\n".join(lines) + "\n"
