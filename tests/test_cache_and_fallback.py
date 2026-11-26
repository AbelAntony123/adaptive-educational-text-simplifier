"""Saved results (cache), the labelled demo fallback and the check-type labels."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from services import backend_adapter as adapter
from services.backend_adapter import simplify
from ui.components import check_kind
from ui.exports import to_json, to_txt
from ui.history import add_entry

TEXT = "Cells are the basic units of life."
APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")

QUOTA_ERROR = {"code": "RATE_LIMIT", "message": "Gemini's per-minute limit was reached. Wait about 30 seconds, then try again."}


def good_raw(level="Beginner", text=TEXT):
    return {
        "original_text": text,
        "simplified_text": "Cells are tiny building blocks of living things.",
        "level": level,
        "verification_status": "PASS",
        "verification_details": [
            {"check": "Numbers, names, and technical terms", "status": "PASS", "explanation": "ok"},
            {"check": "Model factuality review", "status": "PASS", "explanation": "ok"},
        ],
        "metrics": {
            "readability_score": 70.0,
            "semantic_similarity": 0.9,
            "word_count_original": 7,
            "word_count_simplified": 8,
        },
        "attempts": 1,
        "errors": [],
    }


class FakeBackend:
    """Stands in for the real backend and counts how often it is called."""

    def __init__(self, responder=None):
        self.calls = 0
        self.responder = responder or (lambda text, level: good_raw(level, text))

    def __call__(self, text, level):
        self.calls += 1
        return self.responder(text, level)


@pytest.fixture
def backend(monkeypatch):
    fake = FakeBackend()
    monkeypatch.setattr(adapter, "_load_real_backend", lambda: (fake, None))
    return fake


def quota_response(text, level):
    raw = good_raw(level, text)
    raw.update(simplified_text="", verification_status="NOT RUN", verification_details=[], errors=[QUOTA_ERROR], attempts=1)
    raw["metrics"] = {key: None for key in raw["metrics"]}
    return raw


# ---------- saved results (cache) ----------


def test_a_verified_real_result_is_reused_without_calling_the_backend_again(backend):
    cache = {}
    first = simplify(TEXT, "Beginner", mode="backend", cache=cache)
    second = simplify(TEXT, "Beginner", mode="backend", cache=cache)
    assert backend.calls == 1
    assert first["cached"] is False
    assert second["cached"] is True
    assert any("Reused a saved result" in w for w in second["warnings"])
    assert second["simplified_text"] == first["simplified_text"]


def test_a_different_level_or_text_is_a_new_request(backend):
    cache = {}
    simplify(TEXT, "Beginner", mode="backend", cache=cache)
    simplify(TEXT, "Advanced", mode="backend", cache=cache)
    simplify(TEXT + " More.", "Beginner", mode="backend", cache=cache)
    assert backend.calls == 3


def test_extra_spaces_around_the_text_do_not_defeat_the_cache(backend):
    cache = {}
    simplify(TEXT, "Beginner", mode="backend", cache=cache)
    simplify("  " + TEXT + "\n", "Beginner", mode="backend", cache=cache)
    assert backend.calls == 1


def test_without_a_cache_every_run_calls_the_backend(backend):
    simplify(TEXT, "Beginner", mode="backend")
    simplify(TEXT, "Beginner", mode="backend")
    assert backend.calls == 2


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.update(verification_status="FAIL", verification_details=[{"check": "x", "status": "FAIL", "explanation": "y"}]),
        lambda raw: raw.update(errors=[{"code": "API_ERROR", "message": "Busy."}]),
        lambda raw: raw.update(verification_status="NOT RUN", verification_details=[]),
        lambda raw: raw.update(simplified_text=""),
    ],
)
def test_only_clean_verified_results_are_saved(monkeypatch, mutate):
    def responder(text, level):
        raw = good_raw(level, text)
        mutate(raw)
        return raw

    fake = FakeBackend(responder)
    monkeypatch.setattr(adapter, "_load_real_backend", lambda: (fake, None))
    cache = {}
    simplify(TEXT, "Beginner", mode="backend", cache=cache)
    simplify(TEXT, "Beginner", mode="backend", cache=cache)
    assert cache == {}
    assert fake.calls == 2


def test_changing_the_model_setting_invalidates_saved_results(backend, monkeypatch):
    cache = {}
    simplify(TEXT, "Beginner", mode="backend", cache=cache)
    monkeypatch.setenv("GEMINI_MODEL", "some-other-model")
    simplify(TEXT, "Beginner", mode="backend", cache=cache)
    assert backend.calls == 2


def test_mock_results_are_never_cached():
    cache = {}
    simplify(TEXT, "Beginner", mode="mock", cache=cache)
    assert cache == {}


def test_the_cache_is_bounded(backend):
    cache = {}
    for number in range(adapter.CACHE_LIMIT + 5):
        simplify(f"Text number {number}.", "Beginner", mode="backend", cache=cache)
    assert len(cache) == adapter.CACHE_LIMIT


def test_changing_a_reused_result_does_not_change_the_saved_copy(backend):
    cache = {}
    simplify(TEXT, "Beginner", mode="backend", cache=cache)
    reused = simplify(TEXT, "Beginner", mode="backend", cache=cache)
    reused["simplified_text"] = "tampered"
    again = simplify(TEXT, "Beginner", mode="backend", cache=cache)
    assert again["simplified_text"] != "tampered"


# ---------- fallback to demo data ----------


def test_quota_exhaustion_falls_back_to_clearly_labelled_demo_data(monkeypatch):
    fake = FakeBackend(quota_response)
    monkeypatch.setattr(adapter, "_load_real_backend", lambda: (fake, None))
    result = simplify(TEXT, "Beginner", mode="backend", fallback_to_mock=True)
    assert result["source"] == "mock"
    assert result["simplified_text"].startswith("[MOCK]")
    assert "quota ran out" in result["fallback_notice"]
    assert "Wait about 30 seconds" in result["fallback_notice"]
    assert "not real model output" in result["fallback_notice"]


def test_without_the_fallback_switch_the_real_error_is_returned(monkeypatch):
    fake = FakeBackend(quota_response)
    monkeypatch.setattr(adapter, "_load_real_backend", lambda: (fake, None))
    result = simplify(TEXT, "Beginner", mode="backend", fallback_to_mock=False)
    assert result["source"] == "backend"
    assert result["errors"][0]["code"] == "RATE_LIMIT"
    assert result["simplified_text"] == ""
    assert result["fallback_notice"] is None


def test_real_text_is_never_replaced_by_demo_data(monkeypatch):
    def responder(text, level):
        raw = good_raw(level, text)
        raw.update(verification_status="NOT RUN", errors=[QUOTA_ERROR])  # the review hit the quota, text exists
        return raw

    fake = FakeBackend(responder)
    monkeypatch.setattr(adapter, "_load_real_backend", lambda: (fake, None))
    result = simplify(TEXT, "Beginner", mode="backend", fallback_to_mock=True)
    assert result["source"] == "backend"
    assert result["simplified_text"].startswith("Cells are tiny")
    assert result["fallback_notice"] is None


def test_other_errors_do_not_trigger_the_fallback(monkeypatch):
    def responder(text, level):
        raw = quota_response(text, level)
        raw["errors"] = [{"code": "API_AUTH_ERROR", "message": "Check the API key."}]
        return raw

    fake = FakeBackend(responder)
    monkeypatch.setattr(adapter, "_load_real_backend", lambda: (fake, None))
    result = simplify(TEXT, "Beginner", mode="backend", fallback_to_mock=True)
    assert result["source"] == "backend"
    assert result["errors"][0]["code"] == "API_AUTH_ERROR"


def test_demo_fallback_is_not_saved_in_the_cache(monkeypatch):
    fake = FakeBackend(quota_response)
    monkeypatch.setattr(adapter, "_load_real_backend", lambda: (fake, None))
    cache = {}
    simplify(TEXT, "Beginner", mode="backend", cache=cache, fallback_to_mock=True)
    assert cache == {}


def test_fallback_is_not_used_for_a_backend_that_is_not_connected(monkeypatch):
    monkeypatch.delenv(adapter.BACKEND_MODULE_ENV, raising=False)
    result = simplify(TEXT, "Beginner", mode="backend", fallback_to_mock=True)
    assert result["source"] == "backend"
    assert result["errors"][0]["code"] == "BACKEND_UNAVAILABLE"


def test_exports_mention_the_fallback_and_reuse(monkeypatch):
    fake = FakeBackend(quota_response)
    monkeypatch.setattr(adapter, "_load_real_backend", lambda: (fake, None))
    fallback = add_entry({}, simplify(TEXT, "Beginner", mode="backend", fallback_to_mock=True))
    assert "quota ran out" in to_txt(fallback)
    assert "quota ran out" in to_json(fallback)

    monkeypatch.setattr(adapter, "_load_real_backend", lambda: (FakeBackend(), None))
    cache = {}
    simplify(TEXT, "Beginner", mode="backend", cache=cache)
    reused = add_entry({}, simplify(TEXT, "Beginner", mode="backend", cache=cache))
    assert '"reused_saved_result": true' in to_json(reused)
    assert "reused a saved result" in to_txt(reused)


# ---------- real versus simulated checks ----------


def test_check_types_are_labelled():
    assert check_kind("Numbers, names, and technical terms", "backend") == "Local check"
    assert check_kind("Output length sanity", "backend") == "Local check"
    assert check_kind("Simplification effect", "backend") == "Local check"
    assert check_kind("Model factuality review", "backend") == "Gemini review"
    assert check_kind("Meaning preservation review", "backend") == "Gemini review"
    assert check_kind("Something new", "backend") == "Backend check"


def test_every_demo_check_is_labelled_simulated():
    result = simplify(TEXT, "Beginner", mode="mock")
    assert result["verification_details"]
    assert {check_kind(d["check"], result["source"]) for d in result["verification_details"]} == {"Simulated"}


# ---------- in the app ----------


def run_app(monkeypatch, fake):
    monkeypatch.setattr(adapter, "_load_real_backend", lambda: (fake, None))
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    at.radio(key="mode").set_value("Real backend").run()
    at.text_area(key="input_text").set_value(TEXT)
    return at


def click(at):
    at.button(key="simplify_button").click().run()
    assert not at.exception
    return at


def test_app_shows_the_toggles_only_for_the_real_backend(monkeypatch):
    at = AppTest.from_file(APP_PATH, default_timeout=30).run()
    assert len(at.toggle) == 0
    at.radio(key="mode").set_value("Real backend").run()
    assert at.toggle(key="use_cache").value is True
    assert at.toggle(key="use_fallback").value is True


def test_app_labels_a_demo_fallback_and_never_calls_it_real(monkeypatch):
    fake = FakeBackend(quota_response)
    at = click(run_app(monkeypatch, fake))
    entry = at.session_state["current_entry"]
    assert entry["source"] == "mock"
    assert entry["fallback_notice"]
    assert any("Quota used up, so this is demo data" in w.value for w in at.warning)
    badges = "\n".join(m.value for m in at.markdown if "badge" in m.value)
    assert "DEMO FALLBACK" in badges and "MOCK DATA" in badges and "REAL BACKEND" not in badges


def test_app_shows_the_real_error_when_the_fallback_is_switched_off(monkeypatch):
    fake = FakeBackend(quota_response)
    at = run_app(monkeypatch, fake)
    at.toggle(key="use_fallback").set_value(False).run()
    at = click(at)
    assert at.session_state["current_entry"]["source"] == "backend"
    assert any("RATE_LIMIT" in e.value for e in at.error)
    assert any("What you can do" in i.value for i in at.info)


def test_app_reuses_a_saved_result_and_says_so(monkeypatch):
    fake = FakeBackend()
    at = click(run_app(monkeypatch, fake))
    at = click(at)
    assert fake.calls == 1
    assert at.session_state["current_entry"]["cached"] is True
    badges = "\n".join(m.value for m in at.markdown if "badge" in m.value)
    assert "REUSED RESULT" in badges
    assert len(at.session_state["result_cache"]) == 1


def test_app_runs_again_when_saved_results_are_switched_off(monkeypatch):
    fake = FakeBackend()
    at = run_app(monkeypatch, fake)
    at.toggle(key="use_cache").set_value(False).run()
    at = click(at)
    at = click(at)
    assert fake.calls == 2


def test_app_labels_real_and_local_checks_in_the_table(monkeypatch):
    at = click(run_app(monkeypatch, FakeBackend()))
    table = at.table[0].value
    types = dict(zip(table["Check"], table["Type"]))
    assert types["Numbers, names, and technical terms"] == "Local check"
    assert types["Model factuality review"] == "Gemini review"
