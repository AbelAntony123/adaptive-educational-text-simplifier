import time

import pytest

from services import backend_adapter as adapter
from services.backend_adapter import LEVELS, METRIC_KEYS, normalize_response, simplify, validate_input
from services.mock_data import MOCK_SCENARIOS, SAMPLE_TEXT

TEXT = "Cells are the basic units of life."


def valid_raw(**overrides):
    raw = {
        "original_text": TEXT,
        "simplified_text": "Cells are tiny building blocks of living things.",
        "level": "Beginner",
        "verification_status": "PASS",
        "verification_details": [{"check": "Facts", "status": "PASS", "explanation": "ok"}],
        "metrics": {
            "readability_score": 70.0,
            "semantic_similarity": 0.9,
            "word_count_original": 7,
            "word_count_simplified": 8,
        },
        "attempts": 1,
        "errors": [],
    }
    raw.update(overrides)
    return raw


# ---------- input validation ----------


@pytest.mark.parametrize("text", ["", "   ", "\n\t", None, 42])
def test_empty_or_invalid_text_is_rejected(text):
    assert validate_input(text, "Beginner")


def test_too_long_text_is_rejected():
    assert validate_input("a" * (adapter.MAX_INPUT_CHARS + 1), "Beginner")


def test_unknown_level_is_rejected():
    assert validate_input(TEXT, "beginner")  # exact, case-sensitive labels
    assert validate_input(TEXT, "Expert")


@pytest.mark.parametrize("level", LEVELS)
def test_valid_input_has_no_problems(level):
    assert validate_input(TEXT, level) == []


def test_simplify_with_empty_text_returns_error_result_without_calling_backend():
    result = simplify("", "Beginner")
    assert result["errors"][0]["code"] == "INVALID_INPUT"
    assert result["verification_status"] == "NOT RUN"
    assert result["simplified_text"] == ""


# ---------- mock mode ----------


@pytest.mark.parametrize("level", LEVELS)
def test_mock_mode_works_for_all_levels_and_is_labeled(level):
    result = simplify(SAMPLE_TEXT, level, mode="mock")
    assert result["source"] == "mock"
    assert result["level"] == level
    assert result["simplified_text"].startswith("[MOCK]")
    assert result["errors"] == []
    assert result["verification_status"] == "PASS"


def test_mock_word_counts_are_computed_from_the_real_texts():
    result = simplify(SAMPLE_TEXT, "Beginner", mode="mock")
    assert result["metrics"]["word_count_original"] == len(SAMPLE_TEXT.split())
    assert result["metrics"]["word_count_simplified"] == len(result["simplified_text"].split())


def test_every_mock_scenario_returns_a_complete_result():
    for scenario in MOCK_SCENARIOS.values():
        result = simplify(SAMPLE_TEXT, "Intermediate", mode="mock", scenario=scenario)
        assert set(result["metrics"]) == set(METRIC_KEYS)
        assert result["verification_status"] in ("PASS", "FAIL", "NOT RUN")
        assert result["source"] == "mock"


def test_mock_verification_failed_scenario_shows_fail():
    result = simplify(SAMPLE_TEXT, "Beginner", mode="mock", scenario="verification_failed")
    assert result["verification_status"] == "FAIL"


def test_mock_verification_not_run_scenario_never_shows_pass():
    result = simplify(SAMPLE_TEXT, "Beginner", mode="mock", scenario="verification_not_run")
    assert result["verification_status"] == "NOT RUN"
    assert result["verification_details"] == []


def test_mock_missing_metrics_stay_none_not_zero():
    result = simplify(SAMPLE_TEXT, "Beginner", mode="mock", scenario="missing_metrics")
    assert result["metrics"]["readability_score"] is None
    assert result["metrics"]["semantic_similarity"] is None


def test_mock_backend_error_scenario_reports_error_and_no_text():
    result = simplify(SAMPLE_TEXT, "Beginner", mode="mock", scenario="backend_error")
    assert result["errors"]
    assert result["simplified_text"] == ""
    assert result["verification_status"] == "NOT RUN"


def test_mock_exception_scenario_is_caught():
    result = simplify(SAMPLE_TEXT, "Beginner", mode="mock", scenario="exception")
    assert result["errors"][0]["code"] == "BACKEND_EXCEPTION"
    assert result["verification_status"] == "NOT RUN"


def test_mock_malformed_scenario_is_cleaned_up_safely():
    result = simplify(SAMPLE_TEXT, "Beginner", mode="mock", scenario="malformed")
    assert result["verification_status"] == "NOT RUN"
    assert result["simplified_text"] == ""
    assert all(value is None for value in result["metrics"].values())
    assert result["attempts"] is None
    assert result["warnings"]


# ---------- real backend mode (no real backend exists yet) ----------


def test_backend_mode_without_configuration_reports_unavailable(monkeypatch):
    monkeypatch.delenv(adapter.BACKEND_MODULE_ENV, raising=False)
    result = simplify(TEXT, "Beginner", mode="backend")
    assert result["source"] == "backend"
    assert result["errors"][0]["code"] == "BACKEND_UNAVAILABLE"
    assert result["verification_status"] == "NOT RUN"


def test_backend_mode_with_missing_module(monkeypatch):
    monkeypatch.setenv(adapter.BACKEND_MODULE_ENV, "no_such_backend_module_xyz")
    result = simplify(TEXT, "Beginner", mode="backend")
    assert result["errors"][0]["code"] == "BACKEND_UNAVAILABLE"


def test_backend_mode_with_module_lacking_function(monkeypatch):
    monkeypatch.setenv(adapter.BACKEND_MODULE_ENV, "json")  # real module, no simplify_text
    result = simplify(TEXT, "Beginner", mode="backend")
    assert result["errors"][0]["code"] == "BACKEND_UNAVAILABLE"


def test_backend_mode_calls_the_configured_function(monkeypatch):
    calls = []

    def fake_simplify_text(original_text, level):
        calls.append((original_text, level))
        return valid_raw()

    monkeypatch.setattr(adapter, "_load_real_backend", lambda: (fake_simplify_text, None))
    result = simplify(TEXT, "Beginner", mode="backend")
    assert calls == [(TEXT, "Beginner")]
    assert result["source"] == "backend"
    assert result["verification_status"] == "PASS"


def test_backend_exception_becomes_error_result(monkeypatch):
    def boom(original_text, level):
        raise ValueError("model exploded")

    monkeypatch.setattr(adapter, "_load_real_backend", lambda: (boom, None))
    result = simplify(TEXT, "Beginner", mode="backend")
    assert result["errors"][0]["code"] == "BACKEND_EXCEPTION"
    assert "model exploded" in result["errors"][0]["message"]


def test_backend_timeout_becomes_error_result(monkeypatch):
    def slow(original_text, level):
        time.sleep(1)
        return valid_raw()

    monkeypatch.setattr(adapter, "_load_real_backend", lambda: (slow, None))
    result = simplify(TEXT, "Beginner", mode="backend", timeout=0.05)
    assert result["errors"][0]["code"] == "BACKEND_TIMEOUT"


# ---------- response validation ----------


def test_valid_response_passes_through():
    result = normalize_response(valid_raw(), TEXT, "Beginner", "backend")
    assert result["verification_status"] == "PASS"
    assert result["metrics"]["readability_score"] == 70.0
    assert result["warnings"] == []


@pytest.mark.parametrize("raw", [None, "text", 5, [], ["a"]])
def test_non_dict_response_is_invalid(raw):
    result = normalize_response(raw, TEXT, "Beginner", "backend")
    assert result["errors"][0]["code"] == "INVALID_RESPONSE"
    assert result["verification_status"] == "NOT RUN"


def test_empty_dict_response_is_safe():
    result = normalize_response({}, TEXT, "Advanced", "backend")
    assert result["verification_status"] == "NOT RUN"
    assert result["level"] == "Advanced"
    assert result["original_text"] == TEXT
    assert result["simplified_text"] == ""
    assert all(value is None for value in result["metrics"].values())
    assert result["attempts"] is None


def test_missing_metrics_are_none_never_zero():
    raw = valid_raw(metrics={"readability_score": None})
    metrics = normalize_response(raw, TEXT, "Beginner", "backend")["metrics"]
    assert all(value is None for value in metrics.values())


@pytest.mark.parametrize("bad", ["high", True, float("nan"), float("inf"), [1], {}])
def test_invalid_metric_values_become_none(bad):
    raw = valid_raw(metrics={"readability_score": bad, "semantic_similarity": bad})
    result = normalize_response(raw, TEXT, "Beginner", "backend")
    assert result["metrics"]["readability_score"] is None
    assert result["metrics"]["semantic_similarity"] is None


def test_zero_is_kept_as_a_real_value():
    raw = valid_raw(metrics={"readability_score": 0, "semantic_similarity": 0.0, "word_count_original": 0})
    metrics = normalize_response(raw, TEXT, "Beginner", "backend")["metrics"]
    assert metrics["readability_score"] == 0.0
    assert metrics["semantic_similarity"] == 0.0
    assert metrics["word_count_original"] == 0


@pytest.mark.parametrize("bad", [-3, 2.5, "7", True])
def test_invalid_word_counts_become_none(bad):
    raw = valid_raw(metrics={"word_count_original": bad})
    assert normalize_response(raw, TEXT, "Beginner", "backend")["metrics"]["word_count_original"] is None


def test_metrics_not_a_dict_become_na():
    result = normalize_response(valid_raw(metrics="n/a"), TEXT, "Beginner", "backend")
    assert all(value is None for value in result["metrics"].values())
    assert result["warnings"]


@pytest.mark.parametrize("status", [None, "MAYBE", "pass", 1])
def test_unrecognised_status_becomes_not_run(status):
    result = normalize_response(valid_raw(verification_status=status), TEXT, "Beginner", "backend")
    assert result["verification_status"] == "NOT RUN"


def test_failing_check_forces_overall_fail():
    details = [
        {"check": "A", "status": "PASS", "explanation": "x"},
        {"check": "B", "status": "FAIL", "explanation": "y"},
    ]
    result = normalize_response(valid_raw(verification_details=details), TEXT, "Beginner", "backend")
    assert result["verification_status"] == "FAIL"


def test_pass_without_any_passing_check_is_downgraded():
    details = [{"check": "A", "status": "NOT RUN", "explanation": "x"}]
    result = normalize_response(valid_raw(verification_details=details), TEXT, "Beginner", "backend")
    assert result["verification_status"] == "NOT RUN"


def test_pass_with_no_simplified_text_is_downgraded():
    result = normalize_response(valid_raw(simplified_text=""), TEXT, "Beginner", "backend")
    assert result["verification_status"] == "NOT RUN"


def test_pass_without_details_is_kept_but_flagged():
    result = normalize_response(valid_raw(verification_details=[]), TEXT, "Beginner", "backend")
    assert result["verification_status"] == "PASS"
    assert result["warnings"]


def test_plain_string_details_are_never_treated_as_pass():
    result = normalize_response(valid_raw(verification_details=["looks good"]), TEXT, "Beginner", "backend")
    assert result["verification_details"][0]["status"] == "NOT RUN"
    assert result["verification_status"] == "NOT RUN"


def test_detail_with_invalid_status_becomes_not_run():
    details = [{"check": "A", "status": "OK", "explanation": "x"}]
    result = normalize_response(valid_raw(verification_details=details), TEXT, "Beginner", "backend")
    assert result["verification_details"][0]["status"] == "NOT RUN"


def test_details_not_a_list_are_ignored():
    result = normalize_response(valid_raw(verification_details="fine"), TEXT, "Beginner", "backend")
    assert result["verification_details"] == []


def test_errors_are_normalised():
    raw = valid_raw(errors=[{"code": "E1", "message": "bad"}, "plain text error", {"message": "no code"}])
    errors = normalize_response(raw, TEXT, "Beginner", "backend")["errors"]
    assert errors[0] == {"code": "E1", "message": "bad"}
    assert errors[1] == {"code": "UNSPECIFIED", "message": "plain text error"}
    assert errors[2]["code"] == "UNKNOWN"


def test_invalid_level_in_response_falls_back_to_requested_level():
    result = normalize_response(valid_raw(level="Expert"), TEXT, "Advanced", "backend")
    assert result["level"] == "Advanced"
    assert result["warnings"]


def test_level_mismatch_is_flagged():
    result = normalize_response(valid_raw(level="Advanced"), TEXT, "Beginner", "backend")
    assert any("Advanced" in warning for warning in result["warnings"])


@pytest.mark.parametrize("attempts", ["two", -1, 1.5, True])
def test_invalid_attempts_become_none(attempts):
    result = normalize_response(valid_raw(attempts=attempts), TEXT, "Beginner", "backend")
    assert result["attempts"] is None
