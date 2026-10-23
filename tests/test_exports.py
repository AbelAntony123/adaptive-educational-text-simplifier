import json

from services.backend_adapter import make_error_result, simplify
from services.mock_data import SAMPLE_TEXT
from ui.exports import export_filename, history_to_json, to_json, to_txt
from ui.history import add_entry


def make_entry(scenario="success", level="Beginner"):
    state = {}
    return add_entry(state, simplify(SAMPLE_TEXT, level, mode="mock", scenario=scenario))


def test_json_contains_required_fields():
    data = json.loads(to_json(make_entry()))
    for key in (
        "source",
        "level",
        "verification_status",
        "verification_details",
        "metrics",
        "attempts",
        "errors",
        "original_text",
        "simplified_text",
        "created_at",
    ):
        assert key in data
    assert data["source"] == "mock"
    assert "MOCK" in data["source_description"]
    assert data["level"] == "Beginner"


def test_json_keeps_missing_metrics_as_null_not_zero():
    data = json.loads(to_json(make_entry("missing_metrics")))
    assert data["metrics"]["readability_score"] is None
    assert data["metrics"]["semantic_similarity"] is None


def test_json_only_contains_allowed_fields():
    entry = make_entry()
    entry["api_key"] = "sk-should-not-be-exported"
    entry["_view"] = "current"
    exported = to_json(entry)
    assert "sk-should-not-be-exported" not in exported
    assert "_view" not in exported


def test_txt_labels_mock_source_and_shows_na():
    text = to_txt(make_entry("missing_metrics"))
    assert "MOCK DATA" in text
    assert "Readability score: N/A" in text
    assert "Semantic similarity: N/A" in text
    assert "Verification status: PASS" in text


def test_txt_for_not_run_never_says_pass():
    text = to_txt(make_entry("verification_not_run"))
    assert "Verification status: NOT RUN" in text
    assert "No check details available." in text
    assert "[PASS]" not in text


def test_txt_includes_errors():
    text = to_txt(make_entry("backend_error"))
    assert "MOCK_RATE_LIMIT" in text
    assert "(none)" in text  # no simplified text


def test_export_of_error_result_does_not_crash():
    entry = add_entry({}, make_error_result("hi", "Beginner", "backend", "X", "failed"))
    assert json.loads(to_json(entry))["errors"][0]["code"] == "X"
    assert "X: failed" in to_txt(entry)


def test_filename_contains_level_source_and_extension():
    name = export_filename(make_entry(level="Advanced"), "json")
    assert name.startswith("simplification_advanced_mock_")
    assert name.endswith(".json")


def test_history_export_contains_every_entry():
    state = {}
    add_entry(state, simplify(SAMPLE_TEXT, "Beginner", mode="mock"))
    add_entry(state, simplify(SAMPLE_TEXT, "Advanced", mode="mock"))
    data = json.loads(history_to_json(state["history"]))
    assert [r["level"] for r in data["results"]] == ["Advanced", "Beginner"]
