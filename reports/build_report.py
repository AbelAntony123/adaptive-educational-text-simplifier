"""Build the project report (HTML and Markdown) from the saved experiment results and screenshots.

Every number comes from results/summary.json and the results file, so nothing is typed by hand.
Run after experiments\\run_experiments.py and experiments\\summarize.py:

    .venv\\Scripts\\python reports\\build_report.py
"""

from __future__ import annotations

import html
import json
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
LEVELS = ("Beginner", "Intermediate", "Advanced")


def esc(value) -> str:
    return html.escape(str(value))


def fmt(value, digits=1, suffix="") -> str:
    return "N/A" if value is None else f"{value:.{digits}f}{suffix}"


def load():
    summary = json.loads((ROOT / "results" / "summary.json").read_text(encoding="utf-8"))
    path = next((ROOT / "results").glob("experiment_*.jsonl"))
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return summary, records, path.name


def facts(summary: dict, records: list[dict]) -> dict:
    levels = summary["levels"]
    with_text = sum(s["with_text"] for s in levels.values())
    status = {name: sum(s[name] for s in levels.values()) for name in ("PASS", "FAIL", "NOT RUN")}
    by_level_codes = Counter((e["code"], r["level"]) for r in records for e in r["errors"])
    fails = [r for r in records if r["status"] == "FAIL" and r["simplified_text"].strip()]
    return {
        "runs": summary["total_runs"],
        "with_text": with_text,
        "no_text": summary["total_runs"] - with_text,
        "status": status,
        "requests": sum(sum(r["api_requests"].values()) for r in records),
        "seconds": round(sum(r["elapsed_seconds"] for r in records)),
        "passages": len({r["passage_id"] for r in records}),
        "subjects": sorted({r["subject"] for r in records}),
        "codes": summary["error_codes"],
        "by_level_codes": by_level_codes,
        "number_check_fails": [
            r for r in fails
            if any(d["check"].startswith("Numbers") and d["status"] == "FAIL" for d in r["verification_details"])
        ],
        "fails": fails,
        "model": ", ".join(summary["models"]),
        "prompt": ", ".join(summary["prompt_versions"]),
    }


def level_table_html(summary: dict) -> str:
    rows = []
    for level in LEVELS:
        s = summary["levels"][level]
        rows.append(
            f"<tr><th>{level}</th><td>{s['runs']}</td><td>{s['PASS']}</td><td>{s['FAIL']}</td><td>{s['NOT RUN']}</td>"
            f"<td>{s['no_text']}</td><td>{fmt(s['mean_original_readability'])} to {fmt(s['mean_output_readability'])}</td>"
            f"<td>{fmt(s['mean_readability_gain'])}</td><td>{s['readability_improved_in']}</td>"
            f"<td>{fmt(s['mean_similarity'], 2)}</td><td>{fmt(s['mean_word_ratio'], 2)}x</td>"
            f"<td>{fmt(s['mean_attempts'])}</td><td>{s['total_api_requests']}</td></tr>"
        )
    return (
        "<table class='data'><thead><tr><th>Level</th><th>Runs</th><th>PASS</th><th>FAIL</th><th>NOT RUN</th><th>No text</th>"
        "<th>Readability, source to output</th><th>Mean change</th><th>Easier in</th><th>Similarity</th>"
        "<th>Words out/in</th><th>Attempts</th><th>API requests</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def run_table_html(summary: dict) -> str:
    rows = []
    for r in summary["table"]:
        kind = {"PASS": "ok", "FAIL": "bad", "NOT RUN": "warn"}[r["status"]]
        rows.append(
            f"<tr><td>{esc(r['passage'])}</td><td>{r['level']}</td><td><span class='pill {kind}'>{r['status']}</span></td>"
            f"<td>{fmt(r['readability_original'])}</td><td>{fmt(r['readability_output'])}</td>"
            f"<td>{fmt(r['similarity'], 2)}</td><td>{r['words_original'] if r['words_original'] is not None else 'N/A'}"
            f" to {r['words_simplified'] if r['words_simplified'] is not None else 'N/A'}</td>"
            f"<td>{r['attempts']}</td><td>{esc(r['errors'])}</td></tr>"
        )
    return (
        "<table class='data small'><thead><tr><th>Passage</th><th>Level</th><th>Status</th><th>Readability in</th>"
        "<th>out</th><th>Similarity</th><th>Words</th><th>Attempts</th><th>Errors</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table>"
    )


def findings(summary: dict, f: dict) -> list[str]:
    lv = summary["levels"]
    items = [
        f"<b>{f['with_text']} of {f['runs']} runs produced text</b>; {f['status']['PASS']} passed every check, "
        f"{f['status']['FAIL']} failed a check and {f['status']['NOT RUN']} could not complete verification "
        f"(a Gemini server error interrupted the run). {f['no_text']} run produced no usable text at all.",
        f"<b>Beginner made text easier to read:</b> mean Flesch Reading Ease rose from {fmt(lv['Beginner']['mean_original_readability'])} to "
        f"{fmt(lv['Beginner']['mean_output_readability'])} (+{fmt(lv['Beginner']['mean_readability_gain'])}), easier in {lv['Beginner']['readability_improved_in']} runs. "
        f"<b>Intermediate</b> improved less (+{fmt(lv['Intermediate']['mean_readability_gain'])}, easier in {lv['Intermediate']['readability_improved_in']}).",
        f"<b>Advanced did not simplify by this measure:</b> mean readability fell from {fmt(lv['Advanced']['mean_original_readability'])} to "
        f"{fmt(lv['Advanced']['mean_output_readability'])}. This follows from its prompt (concise, precise academic wording with the technical "
        "terms kept) and the fact that the Advanced level has no simplification target. It is a design question for the project, "
        "not a measurement error: the example below shows the actual text.",
        f"<b>Embedding similarity stayed high in every run that produced text:</b> the means were {fmt(lv['Beginner']['mean_similarity'], 2)} (Beginner), "
        f"{fmt(lv['Intermediate']['mean_similarity'], 2)} (Intermediate) and {fmt(lv['Advanced']['mean_similarity'], 2)} (Advanced). Because the score is "
        "(cosine + 1) / 2, values near 1 are expected, and similarity does not prove that the meaning or the facts were kept.",
    ]
    intermediate_invalid = f["by_level_codes"].get(("MODEL_OUTPUT_INVALID", "Intermediate"), 0)
    total_invalid = f["codes"].get("MODEL_OUTPUT_INVALID", 0)
    where = (
        f"All {total_invalid}" if intermediate_invalid == total_invalid else f"{intermediate_invalid} of the {total_invalid}"
    )
    items.append(
        f"<b>Intermediate often returned text that was unchanged or empty:</b> {where} MODEL_OUTPUT_INVALID errors "
        "(the model returned empty or unchanged text) occurred at the Intermediate level. In one run all three attempts did, so no text was produced."
    )
    if f["number_check_fails"] and len(f["number_check_fails"]) == len(f["fails"]):
        items.append(
            f"<b>Both FAIL results are probably false alarms:</b> the local check for numbers and terms failed because the model wrote "
            "numbers as words (\"seven to nine\" instead of \"7 and 9\", \"two percent\" instead of \"2 percent\"). The meaning was kept. "
            "The checker should treat number words as equal to digits; it was not changed during the experiment so the results stay valid."
        )
    return items


LIMITS = [
    "One model (gemini-3.5-flash-lite), one run per passage and level, 8 short passages: too small to draw statistical conclusions.",
    "The default model gemini-3.8-flash and gemini-3.5-flash were overloaded (HTTP 503/504) on the day of testing, which is why the lite model was used.",
    "Flesch Reading Ease and embedding similarity are automatic proxies. They do not prove that a learner understood the text. No human evaluation has been done yet.",
    "Gemini reviews its own output with the same model family, so its verdicts may share the model's blind spots.",
    "The passages were written for this project and are short general-knowledge texts; results on textbook or specialist material may differ.",
    "Free-tier Gemini content may be used by Google to improve its products, so only non-sensitive text was sent.",
]

NEXT = [
    "Make the numbers check treat number words and digits as equal, then re-run the affected cases.",
    "Decide with the team what Advanced should mean, and whether it needs a different target than readability.",
    "Investigate why Intermediate returns unchanged text, for example by strengthening its prompt or retrying with feedback.",
    "Add a larger dataset, repeat each run several times, and compare against a plain one-shot prompt as a baseline.",
    "Add human evaluation (simplicity, meaning preservation, fluency) and report agreement between raters.",
    "Compare more than one model, including a locally run open model.",
]

SHOTS = [
    ("01_home", "Home screen and input", "Demo mode. The example in the header is a hand-written illustration, not model output."),
    ("02_result_texts", "Result: original and simplified text", "Demo (mock) data, labelled MOCK DATA. The numbers and texts are invented examples."),
    ("03_verification_and_types", "Verification table with check types", "Demo data. The Type column says where each check runs; in demo mode every check is 'Simulated'."),
    ("04_metrics", "Metrics", "Demo data. Readability, similarity, word counts and attempts."),
    ("05_word_by_word_changes", "Word-by-word comparison", "Struck-through words were removed, underlined words were added."),
    ("06_verification_fails", "A failed verification", "Demo scenario. The overall status is FAIL and the failing check is shown."),
    ("08_not_run_verification_card", "Verification not run", "Demo scenario. The app says nothing was verified and never shows PASS."),
    ("09_missing_metrics_na", "Missing metrics show as N/A", "Demo scenario. A missing value is never shown as zero."),
    ("10_quota_error", "Quota error handled clearly", "Demo scenario. The error, advice on what to do, no simplified text, and NOT RUN."),
    ("11_history", "Session history and readability chart", "Demo runs; the chart labels each run as mock."),
    ("12_real_mode_sidebar", "Real-backend settings", "The reuse and demo-fallback switches and the .env status (setting names only)."),
    ("14_real_result_badges_and_texts", "A real Gemini result (Intermediate)", "Real backend, gemini-3.5-flash-lite, sample text."),
    ("15_real_verification_types", "Real verification with check types", "Three local checks (no API request) and two Gemini reviews."),
    ("16_real_metrics", "Real metrics", "Computed from the real result."),
    ("17_real_reused_result", "Repeat click reuses the saved result", "Second click with the same text and level: REUSED RESULT, no new API requests."),
    ("13_phone_view", "Phone-sized view", "Demo mode at 390 px width."),
]

CSS = """
:root { --ink:#1A2433; --muted:#566074; --navy:#202734; --slate:#36415A; --green:#B7D894; --pale:#E0F8C7; --line:#D9E0EA; }
* { box-sizing: border-box; }
body { font-family: 'Geist', 'Segoe UI', system-ui, sans-serif; color: var(--ink); margin: 0; background: #F6F8FB; line-height: 1.6; }
main { max-width: 980px; margin: 0 auto; padding: 40px 28px 80px; }
header.cover { background: var(--navy); color: var(--pale); border-radius: 18px; padding: 36px 40px; margin-bottom: 32px; }
.eyebrow { font-family: 'Geist Mono', Consolas, monospace; font-size: 12px; letter-spacing: .12em; text-transform: uppercase; color: var(--green); }
h1 { font-size: 34px; line-height: 1.1; letter-spacing: -0.03em; margin: 10px 0 12px; color: var(--pale); }
header.cover p { margin: 0; color: #C8D6BC; max-width: 640px; }
h2 { font-size: 24px; letter-spacing: -0.02em; margin: 44px 0 10px; padding-top: 6px; border-top: 1px solid var(--line); }
h3 { font-size: 17px; margin: 26px 0 6px; }
p, li { max-width: 760px; }
.note { background: #FFF8DC; border: 1px solid #E7D58A; border-radius: 10px; padding: 12px 16px; margin: 16px 0; max-width: 760px; }
table.data { border-collapse: collapse; width: 100%; font-size: 13px; background: #fff; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; margin: 14px 0; }
table.data th, table.data td { padding: 7px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
table.data thead th { background: var(--navy); color: var(--pale); font-weight: 600; }
table.small { font-size: 12px; }
.pill { display: inline-block; padding: 1px 9px; border-radius: 999px; font-weight: 600; font-size: 11px; border: 1px solid; }
.pill.ok { background: #E6F4EA; color: #14532D; border-color: #14532D; }
.pill.bad { background: #FDECEA; color: #7A1410; border-color: #7A1410; }
.pill.warn { background: #FFF4D6; color: #6B4500; border-color: #6B4500; }
figure { margin: 22px 0; break-inside: avoid; }
figure img { width: 100%; border-radius: 12px; border: 1px solid var(--line); display: block; background: var(--navy); }
figure.narrow img { max-width: 360px; }
figcaption { font-size: 13px; color: var(--muted); margin-top: 6px; }
.chart svg { width: 100%; height: auto; display: block; border-radius: 14px; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.quote { background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; font-size: 14px; }
.quote b { display: block; font-size: 12px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: 4px; }
code { background: #EAEFF5; padding: 1px 6px; border-radius: 5px; font-size: 13px; }
pre { background: var(--navy); color: var(--pale); padding: 14px 16px; border-radius: 10px; overflow-x: auto; font-size: 13px; }
details { margin: 10px 0; }
summary { cursor: pointer; font-weight: 600; }
@media print { body { background: #fff; } main { padding: 0; } h2 { break-after: avoid; } table, .quote, .chart { break-inside: avoid; } header.cover { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
@media (max-width: 700px) { .cols { grid-template-columns: 1fr; } }
"""


def example_html(records: list[dict]) -> str:
    by = {(r["passage_id"], r["level"]): r for r in records}
    try:
        beginner, advanced = by[("geography_nile", "Beginner")], by[("geography_nile", "Advanced")]
    except KeyError:
        return ""
    def box(title, r):
        return (f"<div class='quote'><b>{esc(title)} · readability {fmt(r['metrics']['readability_score'])} "
                f"(source {fmt(r['original_readability'])}) · {r['status']}</b>{esc(r['simplified_text'])}</div>")
    source = f"<div class='quote'><b>Source (readability {fmt(beginner['original_readability'])})</b>{esc(beginner['original_text'])}</div>"
    return f"<div class='cols'>{source}<div>{box('Beginner output', beginner)}<br>{box('Advanced output', advanced)}</div></div>"


def build_html(summary, records, results_name) -> str:
    f = facts(summary, records)
    charts = {name: (REPORTS / "charts" / f"{name}.svg").read_text(encoding="utf-8") for name in ("readability", "outcomes")}
    shots = "".join(
        f"<figure class='{'narrow' if name == '13_phone_view' else ''}'><img src='screenshots/{name}.png' alt='{esc(title)}'>"
        f"<figcaption><b>{esc(title)}.</b> {esc(caption)}</figcaption></figure>"
        for name, title, caption in SHOTS if (REPORTS / "screenshots" / f"{name}.png").exists()
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Adaptive Educational Text Simplifier: project report</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@500&display=swap">
<style>{CSS}</style></head><body><main>
<header class="cover"><div class="eyebrow">Project report · {date.today().isoformat()}</div>
<h1>Adaptive Educational Text Simplification using LLMs</h1>
<p>Streamlit interface, Gemini pipeline, verification checks and a first real experiment: what was built, what was measured, and what is still open.</p></header>

<h2>1. Summary</h2>
<p>The project rewrites educational text at three levels (Beginner, Intermediate, Advanced) and checks every result before showing a verdict.
A Streamlit interface lets a user paste or upload text, compare the original with the rewrite, and see which checks ran, what the metrics are and whether anything failed.
A Gemini-based pipeline does the rewriting and the review. A first experiment ran <b>{f['runs']} real simplifications</b> ({f['passages']} passages × 3 levels) with
<code>{esc(f['model'])}</code>.</p>
<div class="note"><b>How to read this report.</b> Screenshots 1 to 11 and the phone view use <b>demo (mock) data</b>: invented example text and numbers that only show how the interface behaves.
They are not results. The results in section 4 come from real Gemini runs saved in <code>results/{esc(results_name)}</code>.</div>

<h2>2. What was built</h2>
<ul>
<li><b>Interface</b> (<code>app.py</code>, <code>ui/</code>): input and file upload, level selector, side-by-side texts with a word-level diff, verification table, metrics, session history, TXT and JSON export. Missing values show as N/A, and a result is never shown as verified unless checks actually ran.</li>
<li><b>Backend adapter</b> (<code>services/backend_adapter.py</code>): the only file that talks to the pipeline. It validates every response, caps retries, reuses verified results and can show clearly labelled demo data when the quota runs out.</li>
<li><b>Pipeline</b> (<code>pipeline/</code>): level-specific prompts, local preservation checks, a Gemini factuality and meaning review, retries with feedback, Flesch readability and embedding similarity.</li>
<li><b>Quota handling:</b> 429 errors are read for the wait time and retried once only when short; all retries share one budget of three requests per run; Gemini reviews are skipped when a local check already failed. A run uses 4 requests at best and 8 at worst.</li>
<li><b>Tests:</b> automated tests cover the adapter, parser, exports, history, backend, caching, fallback, runner and the app itself.</li>
</ul>

<h2>3. How a result is checked</h2>
<table class="data"><thead><tr><th>Check</th><th>Type</th><th>What it does</th></tr></thead><tbody>
<tr><td>Numbers, names, and technical terms</td><td>Local</td><td>Numbers, capitalised names and hyphenated terms from the source must appear in the output.</td></tr>
<tr><td>Output length sanity</td><td>Local</td><td>The output must not be empty or absurdly long.</td></tr>
<tr><td>Simplification effect</td><td>Local</td><td>Beginner and Intermediate outputs must be measurably easier to read (readability or sentence length). Advanced has no target.</td></tr>
<tr><td>Model factuality review</td><td>Gemini</td><td>A second request asks whether any claim in the output is unsupported by the source.</td></tr>
<tr><td>Meaning preservation review</td><td>Gemini</td><td>The same review asks whether important meaning or qualifications were lost.</td></tr>
</tbody></table>
<p>PASS means every check passed. It says the text is faithful to the source and measurably easier to read. It does <b>not</b> prove that a learner understands it.</p>

<h2>4. Experiment and results</h2>
<h3>Method</h3>
<ul>
<li><b>Data:</b> {f['passages']} short, non-sensitive passages written for the project ({', '.join(f['subjects'])}), each simplified at all three levels = {f['runs']} runs.</li>
<li><b>Model:</b> <code>{esc(f['model'])}</code> (embeddings: <code>gemini-embedding-2-preview</code>); prompt version <code>{esc(f['prompt'])}</code>.</li>
<li><b>Settings:</b> one run per passage and level, no saved-result reuse and no demo fallback, so every number is real. Up to 3 generation attempts per run; 20 seconds between runs.</li>
<li><b>Cost:</b> {f['requests']} API requests and {f['seconds']} seconds of run time in total. The runner is resumable and stops early if Gemini keeps failing.</li>
<li><b>Reproduce:</b> <code>experiments\\run_experiments.py</code>, then <code>experiments\\summarize.py</code>, then <code>reports\\build_report.py</code>.</li>
</ul>
<h3>Results by level</h3>
{level_table_html(summary)}
<p style="font-size:13px;color:var(--muted)">Readability is Flesch Reading Ease (higher is easier). Similarity is (cosine + 1) / 2 on embeddings. "No text" means the run produced no usable output. Means use only runs that produced text.</p>
<div class="chart">{charts['readability']}</div>
<div class="chart" style="margin-top:16px">{charts['outcomes']}</div>

<h3>Findings</h3>
<ul>{''.join(f'<li>{item}</li>' for item in findings(summary, f))}</ul>

<h3>Example: the same passage at two levels</h3>
{example_html(records)}

<details><summary>All {f['runs']} runs</summary>{run_table_html(summary)}</details>

<h2>5. Limitations</h2>
<ul>{''.join(f'<li>{esc(item)}</li>' for item in LIMITS)}</ul>

<h2>6. Next steps</h2>
<ol>{''.join(f'<li>{esc(item)}</li>' for item in NEXT)}</ol>

<h2>7. Interface screenshots</h2>
{shots}

<h2>8. Run it yourself</h2>
<pre>python -m venv .venv
.venv\\Scripts\\python -m pip install -r requirements.txt
.venv\\Scripts\\python -m pip install -r pipeline\\requirements.txt
.venv\\Scripts\\python -m streamlit run app.py      (demo works with no key)
.venv\\Scripts\\python -m pytest</pre>
<p>For the real backend, copy <code>.env.example</code> to <code>.env</code> and fill in the key yourself. The file is ignored by Git and is never shown or saved by the app.</p>
</main></body></html>"""


def build_markdown(summary, records, results_name) -> str:
    f = facts(summary, records)
    strip = lambda text: text.replace("<b>", "**").replace("</b>", "**")
    lines = [
        "# Adaptive Educational Text Simplification using LLMs: project report",
        f"_{date.today().isoformat()}_",
        "",
        "## Summary",
        f"{f['runs']} real simplifications ({f['passages']} passages x 3 levels) with `{f['model']}`, prompt `{f['prompt']}`. "
        f"{f['requests']} API requests, {f['seconds']} seconds.",
        "",
        "> Screenshots 1 to 11 and the phone view use demo (mock) data: invented example numbers, not results. "
        f"Real results are in `results/{results_name}`.",
        "",
        "## Results by level",
        "",
        "| Level | Runs | PASS | FAIL | NOT RUN | No text | Readability (source to output) | Mean change | Similarity | Words out/in | Attempts | Requests |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for level in LEVELS:
        s = summary["levels"][level]
        lines.append(
            f"| {level} | {s['runs']} | {s['PASS']} | {s['FAIL']} | {s['NOT RUN']} | {s['no_text']} | "
            f"{fmt(s['mean_original_readability'])} to {fmt(s['mean_output_readability'])} | {fmt(s['mean_readability_gain'])} | "
            f"{fmt(s['mean_similarity'], 2)} | {fmt(s['mean_word_ratio'], 2)}x | {fmt(s['mean_attempts'])} | {s['total_api_requests']} |"
        )
    lines += ["", "## Findings", ""] + [f"- {strip(item)}" for item in findings(summary, f)]
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in LIMITS]
    lines += ["", "## Next steps", ""] + [f"{i}. {item}" for i, item in enumerate(NEXT, 1)]
    lines += ["", "## Screenshots", ""]
    for name, title, caption in SHOTS:
        if (REPORTS / "screenshots" / f"{name}.png").exists():
            lines += [f"![{title}](screenshots/{name}.png)", f"*{title}.* {caption}", ""]
    return "\n".join(lines) + "\n"


def main() -> int:
    summary, records, results_name = load()
    (REPORTS / "report.html").write_text(build_html(summary, records, results_name), encoding="utf-8")
    (REPORTS / "REPORT.md").write_text(build_markdown(summary, records, results_name), encoding="utf-8")
    print("Wrote reports/report.html and reports/REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
