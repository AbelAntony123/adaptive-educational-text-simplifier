import json

import pytest

from experiments import run_experiments as runner
from experiments import summarize as summ


def record(passage="p1", level="Beginner", status="PASS", text="Simple text.", readability=60.0, original=30.0,
           similarity=0.9, words=(20, 25), attempts=1, requests=None, errors=None, source="backend",
           model="m", prompt="v1", details=None):
    return {
        "run_key": runner.run_key(passage, level, model, prompt),
        "passage_id": passage,
        "subject": "Subject",
        "level": level,
        "model": model,
        "prompt_version": prompt,
        "source": source,
        "status": status,
        "attempts": attempts,
        "api_requests": requests or {"generate": 1, "verify": 1, "embed": 2},
        "errors": errors or [],
        "metrics": {
            "readability_score": readability,
            "semantic_similarity": similarity,
            "word_count_original": words[0],
            "word_count_simplified": words[1],
        },
        "original_readability": original,
        "verification_details": details or [],
        "original_text": "Original.",
        "simplified_text": text,
    }


# ---------- runner ----------


def test_the_dataset_is_valid_and_covers_several_subjects():
    passages = runner.load_passages(runner.DEFAULT_PASSAGES)
    assert len(passages) >= 8
    assert len({p["id"] for p in passages}) == len(passages)
    assert len({p["subject"] for p in passages}) >= 6
    assert all(30 <= len(p["text"].split()) <= 120 for p in passages)


def test_plan_covers_every_passage_at_every_level_passage_by_passage():
    passages = [{"id": "a"}, {"id": "b"}]
    plan = runner.plan_runs(passages, ("Beginner", "Advanced"))
    assert [(p["id"], level) for p, level in plan] == [
        ("a", "Beginner"), ("a", "Advanced"), ("b", "Beginner"), ("b", "Advanced"),
    ]


def test_resume_skips_runs_with_text_but_retries_runs_without(tmp_path):
    path = tmp_path / "results.jsonl"
    done = record(passage="a")
    failed = record(passage="b", text="", status="NOT RUN")
    demo = record(passage="c", source="mock")
    path.write_text("\n".join(json.dumps(r) for r in (done, failed, demo)) + "\nnot json\n", encoding="utf-8")
    assert runner.load_done(path) == {done["run_key"]}


def test_resume_with_no_file_is_empty(tmp_path):
    assert runner.load_done(tmp_path / "missing.jsonl") == set()


def test_run_key_changes_with_model_and_prompt_version():
    assert runner.run_key("a", "Beginner", "m1", "v1") != runner.run_key("a", "Beginner", "m2", "v1")
    assert runner.run_key("a", "Beginner", "m1", "v1") != runner.run_key("a", "Beginner", "m1", "v2")


@pytest.mark.parametrize(
    "recent, expected",
    [([], False), ([False] * 3, False), ([False] * 4, True), ([True, False, False, False, False], True),
     ([False, False, False, True], False), ([True] * 6, False)],
)
def test_the_runner_stops_only_after_consecutive_runs_without_text(recent, expected):
    assert runner.should_stop(recent) is expected


def test_dry_run_sends_nothing_and_needs_no_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    code = runner.main(["--dry-run", "--out", str(tmp_path / "r.jsonl")])
    output = capsys.readouterr().out
    assert code == 0
    assert "Dry run, nothing sent." in output
    assert not (tmp_path / "r.jsonl").exists()


def test_without_a_key_nothing_is_sent(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    code = runner.main(["--out", str(tmp_path / "r.jsonl"), "--max-runs", "1"])
    assert code == 1
    assert "Nothing was sent" in capsys.readouterr().out


def test_the_runner_output_never_contains_the_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-key-value")
    runner.main(["--dry-run", "--out", str(tmp_path / "r.jsonl")])
    assert "super-secret-key-value" not in capsys.readouterr().out


# ---------- summarizer ----------


def test_load_records_keeps_only_real_results_and_the_latest_repeat(tmp_path):
    path = tmp_path / "r.jsonl"
    first = record(status="FAIL")
    second = dict(first, status="PASS")
    demo = record(passage="x", source="mock")
    path.write_text("\n".join(json.dumps(r) for r in (first, second, demo)), encoding="utf-8")
    records = summ.load_records(path)
    assert len(records) == 1 and records[0]["status"] == "PASS"


def test_summary_counts_and_means_are_computed_from_the_records():
    records = [
        record("a", "Beginner", "PASS", readability=60.0, original=30.0, similarity=0.9, words=(20, 30)),
        record("b", "Beginner", "FAIL", readability=50.0, original=30.0, similarity=0.7, words=(20, 10)),
        record("c", "Beginner", "NOT RUN", text="", readability=None, similarity=None, words=(20, None)),
    ]
    s = summ.summarize(records)["levels"]["Beginner"]
    assert (s["runs"], s["with_text"], s["no_text"]) == (3, 2, 1)
    assert (s["PASS"], s["FAIL"], s["NOT RUN"]) == (1, 1, 0)  # a NOT RUN run without text counts as "no text"
    assert s["mean_original_readability"] == 30.0
    assert s["mean_output_readability"] == 55.0
    assert s["mean_readability_gain"] == 25.0
    assert s["readability_improved_in"] == "2 of 2"
    assert s["mean_similarity"] == 0.8
    assert s["mean_word_ratio"] == 1.0  # (1.5 + 0.5) / 2
    assert s["total_api_requests"] == 12


def test_missing_values_stay_none_not_zero():
    s = summ.summarize([record(readability=None, similarity=None, text="x")])["levels"]["Beginner"]
    assert s["mean_output_readability"] is None
    assert s["mean_similarity"] is None
    assert s["mean_readability_gain"] is None
    assert summ.summarize([])["levels"]["Advanced"]["mean_similarity"] is None


def test_error_codes_and_failed_checks_are_counted():
    records = [
        record(errors=[{"code": "API_ERROR", "message": "m"}], text=""),
        record("b", errors=[{"code": "API_ERROR", "message": "m"}, {"code": "RATE_LIMIT", "message": "m"}], text=""),
        record("c", status="FAIL", details=[{"check": "Simplification effect", "status": "FAIL", "explanation": "e"},
                                              {"check": "Output length sanity", "status": "PASS", "explanation": "e"}]),
    ]
    summary = summ.summarize(records)
    assert summary["error_codes"] == {"API_ERROR": 2, "RATE_LIMIT": 1}
    assert summary["failed_checks"] == {"Simplification effect": 1}


def test_markdown_and_charts_handle_empty_and_normal_data():
    for records in ([], [record(), record("b", "Advanced")]):
        summary = summ.summarize(records)
        assert "| Level |" in summ.to_markdown(summary)
        for svg in (summ.readability_chart(summary), summ.outcome_chart(summary)):
            assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")


def test_charts_label_values_in_text_and_mark_missing_ones():
    summary = summ.summarize([record(readability=61.2, original=20.3)])
    chart = summ.readability_chart(summary)
    assert "61.2" in chart and "20.3" in chart and "N/A" in chart  # Intermediate and Advanced have no data
    assert "PASS 1" in summ.outcome_chart(summary)
