"""Clearly labeled MOCK responses used while the real backend is not ready.

Nothing in this file is produced by an AI model. The texts and numbers are
hand-written examples that imitate the proposed backend contract so the UI can
be built and tested. They must never be presented as research findings.
"""

from __future__ import annotations

SAMPLE_TEXT = (
    "Photosynthesis is the biochemical process by which autotrophic organisms, "
    "such as plants and algae, convert light energy into chemical energy. "
    "During the light-dependent reactions, chlorophyll absorbs photons, driving "
    "the synthesis of ATP and NADPH, which subsequently power the Calvin cycle, "
    "wherein carbon dioxide is fixed into glucose."
)

# Hand-written examples, only used when the input is exactly SAMPLE_TEXT.
_SAMPLE_OUTPUTS = {
    "Beginner": (
        "[MOCK] Plants make their own food using sunlight. Their green parts "
        "catch the light. The plant uses this light, water, and air to make "
        "sugar. The sugar gives the plant energy to grow."
    ),
    "Intermediate": (
        "[MOCK] Photosynthesis is how plants and algae turn light energy into "
        "chemical energy. Chlorophyll absorbs light, and the plant makes "
        "energy-carrying molecules called ATP and NADPH. These molecules power "
        "the Calvin cycle, where carbon dioxide is turned into glucose."
    ),
    "Advanced": (
        "[MOCK] Photosynthesis is the process by which plants and algae convert "
        "light energy into chemical energy. In the light-dependent reactions, "
        "chlorophyll absorbs photons to produce ATP and NADPH, which then drive "
        "the Calvin cycle, where carbon dioxide is fixed into glucose."
    ),
}

# Invented example numbers, one set per level. They are NOT real measurements.
_MOCK_METRICS = {
    "Beginner": {"readability_score": 82.0, "semantic_similarity": 0.71},
    "Intermediate": {"readability_score": 64.5, "semantic_similarity": 0.86},
    "Advanced": {"readability_score": 48.2, "semantic_similarity": 0.93},
}

# Label shown in the sidebar -> scenario key used below.
MOCK_SCENARIOS = {
    "Normal result (verification passes)": "success",
    "Verification fails": "verification_failed",
    "Verification not run": "verification_not_run",
    "Some metrics missing": "missing_metrics",
    "Backend reports an error": "backend_error",
    "Malformed response": "malformed",
    "Backend crashes (exception)": "exception",
}


def _word_count(text: str) -> int:
    return len(text.split())


def _mock_text_for(original_text: str, level: str) -> str:
    if original_text.strip() == SAMPLE_TEXT and level in _SAMPLE_OUTPUTS:
        return _SAMPLE_OUTPUTS[level]
    return (
        f"[MOCK] Placeholder output for the {level} level. The mock backend "
        "does not read or rewrite your text. A real model would show the "
        "simplified version here."
    )


def _passing_details() -> list[dict]:
    return [
        {
            "check": "Key facts preserved",
            "status": "PASS",
            "explanation": "Mock check: the main facts of the original appear in the simplified text.",
        },
        {
            "check": "No new claims added",
            "status": "PASS",
            "explanation": "Mock check: the simplified text does not add information that is missing from the original.",
        },
        {
            "check": "Reading level matches target",
            "status": "PASS",
            "explanation": "Mock check: the wording matches the selected difficulty level.",
        },
    ]


def mock_simplify_text(original_text: str, level: str, scenario: str = "success"):
    """Imitate ``simplify_text``. Returns a raw response (or raises) per scenario."""
    if scenario == "exception":
        raise RuntimeError("Simulated backend crash (mock scenario).")
    if scenario == "malformed":
        return {
            "simplified_text": 12345,
            "verification_status": "MAYBE",
            "verification_details": ["looks fine"],
            "metrics": "n/a",
            "attempts": "two",
            "errors": "none",
        }

    simplified = _mock_text_for(original_text, level)
    numbers = _MOCK_METRICS.get(level, {"readability_score": None, "semantic_similarity": None})
    response = {
        "original_text": original_text,
        "simplified_text": simplified,
        "level": level,
        "verification_status": "PASS",
        "verification_details": _passing_details(),
        "metrics": {
            "readability_score": numbers["readability_score"],
            "semantic_similarity": numbers["semantic_similarity"],
            "word_count_original": _word_count(original_text),
            "word_count_simplified": _word_count(simplified),
        },
        "attempts": 1,
        "errors": [],
    }

    if scenario == "verification_failed":
        response["verification_status"] = "FAIL"
        response["verification_details"][1] = {
            "check": "No new claims added",
            "status": "FAIL",
            "explanation": "Mock check: a statement appears in the simplified text that is not in the original.",
        }
        response["attempts"] = 3
    elif scenario == "verification_not_run":
        response["verification_status"] = "NOT RUN"
        response["verification_details"] = []
    elif scenario == "missing_metrics":
        response["metrics"]["readability_score"] = None
        response["metrics"]["semantic_similarity"] = None
    elif scenario == "backend_error":
        response["simplified_text"] = ""
        response["verification_status"] = "NOT RUN"
        response["verification_details"] = []
        response["metrics"] = {
            "readability_score": None,
            "semantic_similarity": None,
            "word_count_original": _word_count(original_text),
            "word_count_simplified": None,
        }
        response["attempts"] = 3
        response["errors"] = [
            {"code": "MOCK_RATE_LIMIT", "message": "Simulated error: the model service is busy. Please try again."}
        ]
    return response
