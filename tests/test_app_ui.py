"""Smoke tests that run the real app.py with Streamlit's built-in AppTest."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from services.mock_data import SAMPLE_TEXT

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


def new_app() -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def run_simplify(at: AppTest, text: str = SAMPLE_TEXT, level: str = "Beginner") -> AppTest:
    at.text_area(key="input_text").set_value(text)
    at.radio(key="level").set_value(level)
    at.button(key="simplify_button").click().run()
    return at


def all_text(at: AppTest) -> str:
    parts = []
    for group in (at.markdown, at.success, at.error, at.warning, at.info, at.caption):
        parts += [element.value for element in group]
    parts += [str(metric.value) for metric in at.metric]
    return "\n".join(parts)


def test_app_starts_with_no_errors_and_shows_title():
    at = new_app()
    assert at.title[0].value == "Adaptive Educational Text Simplifier"
    assert at.radio(key="level").options == ["Beginner", "Intermediate", "Advanced"]
    assert "Your result will appear here" in all_text(at)


def test_app_defaults_to_mock_mode():
    at = new_app()
    assert at.radio(key="mode").value == "Demo with mock data"


def test_empty_input_shows_friendly_message_and_no_result():
    at = new_app()
    at.button(key="simplify_button").click().run()
    assert not at.exception
    assert any("enter or upload some text" in e.value for e in at.error)
    assert at.session_state["current_entry"] is None


def test_whitespace_input_is_rejected():
    at = run_simplify(new_app(), text="   \n  ")
    assert any("enter or upload some text" in e.value for e in at.error)


@pytest.mark.parametrize("level", ["Beginner", "Intermediate", "Advanced"])
def test_simplify_in_each_level_shows_mock_banner_and_result(level):
    at = run_simplify(new_app(), level=level)
    assert not at.exception
    text = all_text(at)
    assert "MOCK DATA" in text
    assert "Verification: PASS" in text
    assert at.session_state["current_entry"]["level"] == level
    assert at.session_state["current_entry"]["source"] == "mock"


def test_result_shows_text_status_badges():
    at = run_simplify(new_app())
    badges = "\n".join(m.value for m in at.markdown if "badge" in m.value)
    assert "MOCK DATA" in badges
    assert "Level: Beginner" in badges
    assert "Verification: PASS" in badges


def test_not_run_badge_is_never_labelled_pass():
    at = new_app()
    at.selectbox(key="scenario").select("Verification not run")
    at = run_simplify(at)
    badges = "\n".join(m.value for m in at.markdown if "badge" in m.value)
    assert "Verification: NOT RUN" in badges
    assert "Verification: PASS" not in badges


def test_result_shows_metrics_and_attempts():
    at = run_simplify(new_app())
    labels = {m.label: m.value for m in at.metric}
    assert labels["Readability score"] == "82.0"
    assert labels["Semantic similarity"] == "0.71"
    assert labels["Attempts"] == "1"


def test_missing_metrics_display_na_not_zero():
    at = new_app()
    at.selectbox(key="scenario").select("Some metrics missing")
    at = run_simplify(at)
    labels = {m.label: m.value for m in at.metric}
    assert labels["Readability score"] == "N/A"
    assert labels["Semantic similarity"] == "N/A"


def test_verification_fail_is_shown_as_fail():
    at = new_app()
    at.selectbox(key="scenario").select("Verification fails")
    at = run_simplify(at)
    assert any("Verification: FAIL" in e.value for e in at.error)
    assert not any("Verification: PASS" in e.value for e in at.success)


def test_verification_not_run_never_shown_as_pass():
    at = new_app()
    at.selectbox(key="scenario").select("Verification not run")
    at = run_simplify(at)
    assert any("Verification: NOT RUN" in e.value for e in at.warning)
    assert not any("Verification: PASS" in e.value for e in at.success)


def test_backend_error_message_is_displayed():
    at = new_app()
    at.selectbox(key="scenario").select("Backend reports an error")
    at = run_simplify(at)
    assert not at.exception
    assert any("MOCK_RATE_LIMIT" in e.value for e in at.error)


@pytest.mark.parametrize("scenario", ["Malformed response", "Backend crashes (exception)"])
def test_bad_backend_behaviour_does_not_crash_the_app(scenario):
    at = new_app()
    at.selectbox(key="scenario").select(scenario)
    at = run_simplify(at)
    assert not at.exception
    assert at.session_state["current_entry"]["verification_status"] == "NOT RUN"


def test_real_backend_mode_without_backend_shows_clear_error(monkeypatch):
    monkeypatch.delenv("SIMPLIFIER_BACKEND_MODULE", raising=False)
    at = new_app()
    at.radio(key="mode").set_value("Real backend").run()
    at = run_simplify(at)
    assert not at.exception
    assert any("BACKEND_UNAVAILABLE" in e.value for e in at.error)
    assert not any("MOCK DATA" in w.value for w in at.warning)


def test_history_starts_empty_then_records_runs():
    at = new_app()
    assert at.session_state["history"] == []
    at = run_simplify(at, level="Beginner")
    at = run_simplify(at, level="Advanced")
    levels = [entry["level"] for entry in at.session_state["history"]]
    assert levels == ["Advanced", "Beginner"]


def test_clear_history_button_empties_history():
    at = run_simplify(new_app())
    assert len(at.session_state["history"]) == 1
    at.button(key="history_clear").click().run()
    assert at.session_state["history"] == []
    assert not at.exception
