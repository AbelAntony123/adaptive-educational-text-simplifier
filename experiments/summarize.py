"""Turn the saved experiment results into tables and charts. Every number is computed from the file."""

from __future__ import annotations

import html
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
LEVELS = ("Beginner", "Intermediate", "Advanced")


def load_records(path: Path) -> list[dict]:
    """Real-backend records only. If a run was repeated, the latest record for it wins."""
    latest: dict[str, dict] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("source") == "backend":
            latest[record["run_key"]] = record
    return list(latest.values())


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(mean(values), 3) if values else None


def _word_ratio(record: dict) -> float | None:
    original, simplified = record["metrics"].get("word_count_original"), record["metrics"].get("word_count_simplified")
    return simplified / original if original and simplified is not None else None


def summarize(records: list[dict]) -> dict:
    """Per-level statistics, failure reasons and a per-run table."""
    levels = {}
    for level in LEVELS:
        rows = [r for r in records if r["level"] == level]
        with_text = [r for r in rows if str(r["simplified_text"]).strip()]
        levels[level] = {
            "runs": len(rows),
            "with_text": len(with_text),
            "no_text": len(rows) - len(with_text),
            "PASS": sum(r["status"] == "PASS" for r in with_text),
            "FAIL": sum(r["status"] == "FAIL" for r in with_text),
            "NOT RUN": sum(r["status"] == "NOT RUN" for r in with_text),
            "mean_original_readability": _mean(r["original_readability"] for r in with_text),
            "mean_output_readability": _mean(r["metrics"].get("readability_score") for r in with_text),
            "mean_similarity": _mean(r["metrics"].get("semantic_similarity") for r in with_text),
            "mean_word_ratio": _mean(_word_ratio(r) for r in with_text),
            "mean_attempts": _mean(r["attempts"] for r in rows),
            "mean_api_requests": _mean(sum(r["api_requests"].values()) for r in rows),
            "total_api_requests": sum(sum(r["api_requests"].values()) for r in rows),
        }
        gains = [
            r["metrics"]["readability_score"] - r["original_readability"]
            for r in with_text
            if r["metrics"].get("readability_score") is not None and r["original_readability"] is not None
        ]
        levels[level]["mean_readability_gain"] = round(mean(gains), 2) if gains else None
        levels[level]["readability_improved_in"] = f"{sum(g > 0 for g in gains)} of {len(gains)}"
    error_codes = Counter(e["code"] for r in records for e in r["errors"])
    failed_checks = Counter(
        d["check"] for r in records for d in r["verification_details"] if d["status"] == "FAIL"
    )
    table = [
        {
            "passage": r["passage_id"],
            "subject": r["subject"],
            "level": r["level"],
            "status": r["status"],
            "attempts": r["attempts"],
            "requests": sum(r["api_requests"].values()),
            "readability_original": r["original_readability"],
            "readability_output": r["metrics"].get("readability_score"),
            "similarity": r["metrics"].get("semantic_similarity"),
            "words_original": r["metrics"].get("word_count_original"),
            "words_simplified": r["metrics"].get("word_count_simplified"),
            "errors": ",".join(e["code"] for e in r["errors"]) or "-",
        }
        for r in sorted(records, key=lambda r: (r["passage_id"], LEVELS.index(r["level"])))
    ]
    models = sorted({r["model"] for r in records})
    prompts = sorted({r["prompt_version"] for r in records})
    return {
        "total_runs": len(records),
        "models": models,
        "prompt_versions": prompts,
        "levels": levels,
        "error_codes": dict(error_codes),
        "failed_checks": dict(failed_checks),
        "table": table,
    }


def _fmt(value, digits=2, suffix="") -> str:
    return "N/A" if value is None else f"{value:.{digits}f}{suffix}"


def to_markdown(summary: dict) -> str:
    lines = [
        f"Runs: {summary['total_runs']} | models: {', '.join(summary['models'])} | prompt versions: {', '.join(summary['prompt_versions'])}",
        "",
        "| Level | Runs | PASS | FAIL | NOT RUN | No text | Readability (original to output) | Mean gain | Similarity | Words (output / original) | Attempts | Requests |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for level, s in summary["levels"].items():
        lines.append(
            f"| {level} | {s['runs']} | {s['PASS']} | {s['FAIL']} | {s['NOT RUN']} | {s['no_text']} | "
            f"{_fmt(s['mean_original_readability'], 1)} to {_fmt(s['mean_output_readability'], 1)} | "
            f"{_fmt(s['mean_readability_gain'], 1)} | {_fmt(s['mean_similarity'])} | "
            f"{_fmt(s['mean_word_ratio'])}x | {_fmt(s['mean_attempts'], 1)} | {s['total_api_requests']} |"
        )
    return "\n".join(lines) + "\n"


# ---------- charts (plain SVG, palette colours, always with text labels) ----------

_INK, _MUTED, _BASE, _RAISED, _ACCENT, _TEXT = "#E0F8C7", "#A9B8A0", "#202734", "#36415A", "#B7D894", "#E0F8C7"


def _svg_open(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}" '
        f'font-family="Geist, Inter, Segoe UI, sans-serif">',
        f'<rect width="{width}" height="{height}" rx="14" fill="{_BASE}"/>',
        f'<text x="24" y="34" fill="{_TEXT}" font-size="16" font-weight="600">{html.escape(title)}</text>',
    ]


def readability_chart(summary: dict) -> str:
    """Grouped bars: mean readability of the original texts versus the outputs, per level."""
    width, height, left, bottom, top = 640, 340, 56, 60, 64
    parts = _svg_open(width, height, "Readability by level (Flesch Reading Ease, higher = easier)")
    plot_h = height - top - bottom
    scale = plot_h / 100
    for tick in (0, 25, 50, 75, 100):
        y = height - bottom - tick * scale
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - 24}" y2="{y:.1f}" stroke="{_RAISED}"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.1f}" fill="{_MUTED}" font-size="11" text-anchor="end">{tick}</text>')
    group_w = (width - left - 24) / 3
    for i, level in enumerate(LEVELS):
        s = summary["levels"][level]
        x0 = left + i * group_w + group_w * 0.18
        for j, (label, value, color) in enumerate(
            (("Original", s["mean_original_readability"], _RAISED), ("Output", s["mean_output_readability"], _ACCENT))
        ):
            bar_w = group_w * 0.3
            x = x0 + j * (bar_w + 6)
            if value is None:
                parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{height - bottom - 6}" fill="{_MUTED}" font-size="12" text-anchor="middle">N/A</text>')
                continue
            h = max(value, 0) * scale
            parts.append(f'<rect x="{x:.1f}" y="{height - bottom - h:.1f}" width="{bar_w:.1f}" height="{h:.1f}" rx="4" fill="{color}" stroke="{_ACCENT}" stroke-width="1"/>')
            parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{height - bottom - h - 6:.1f}" fill="{_TEXT}" font-size="12" text-anchor="middle">{value:.1f}</text>')
        parts.append(f'<text x="{left + i * group_w + group_w / 2:.1f}" y="{height - bottom + 22}" fill="{_TEXT}" font-size="13" text-anchor="middle">{level}</text>')
    parts.append(f'<rect x="{left}" y="{height - 22}" width="12" height="12" rx="3" fill="{_RAISED}" stroke="{_ACCENT}"/>')
    parts.append(f'<text x="{left + 18}" y="{height - 12}" fill="{_MUTED}" font-size="12">Original text</text>')
    parts.append(f'<rect x="{left + 120}" y="{height - 22}" width="12" height="12" rx="3" fill="{_ACCENT}"/>')
    parts.append(f'<text x="{left + 138}" y="{height - 12}" fill="{_MUTED}" font-size="12">Simplified output</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def outcome_chart(summary: dict) -> str:
    """Stacked bars: how every run ended, per level (counts, with labels)."""
    width, height, left, top = 640, 300, 120, 60
    parts = _svg_open(width, height, "How each run ended, by level")
    categories = (("PASS", _ACCENT, _BASE), ("FAIL", "#FFB4AB", _BASE), ("NOT RUN", "#F5D78A", _BASE), ("No text", _RAISED, _TEXT))
    max_runs = max((s["runs"] for s in summary["levels"].values()), default=1) or 1
    bar_w = width - left - 40
    for i, level in enumerate(LEVELS):
        s = summary["levels"][level]
        y = top + i * 62
        parts.append(f'<text x="{left - 12}" y="{y + 24}" fill="{_TEXT}" font-size="13" text-anchor="end">{level}</text>')
        x = left
        for name, fill, label_color in categories:
            count = s["no_text"] if name == "No text" else s[name]
            if not count:
                continue
            w = count / max_runs * bar_w
            parts.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="36" fill="{fill}" stroke="{_BASE}"/>')
            parts.append(f'<text x="{x + w / 2:.1f}" y="{y + 23}" fill="{label_color}" font-size="13" font-weight="600" text-anchor="middle">{name} {count}</text>')
            x += w
    parts.append("</svg>")
    return "\n".join(parts)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("Usage: summarize.py results\\experiment_<model>.jsonl")
        return 1
    records = load_records(Path(argv[0]))
    summary = summarize(records)
    results_dir = ROOT / "results"
    charts_dir = ROOT / "reports" / "charts"
    results_dir.mkdir(exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (results_dir / "summary.md").write_text(to_markdown(summary), encoding="utf-8")
    (charts_dir / "readability.svg").write_text(readability_chart(summary), encoding="utf-8")
    (charts_dir / "outcomes.svg").write_text(outcome_chart(summary), encoding="utf-8")
    print(to_markdown(summary))
    print("Error codes seen:", summary["error_codes"] or "none")
    print("Checks that failed:", summary["failed_checks"] or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
