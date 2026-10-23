"""Reusable Streamlit pieces: banners, results, verification, metrics, history."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from services.backend_adapter import SOURCE_BACKEND, SOURCE_MOCK
from ui.diff import word_diff_html
from ui.exports import export_filename, history_to_json, to_json, to_txt
from ui.theme import badge, badge_row, status_badge, text_box

LEVEL_HELP = {
    "Beginner": "Simplest wording, for readers new to the topic.",
    "Intermediate": "Plainer wording while keeping more of the detail.",
    "Advanced": "Light simplification that keeps most technical detail.",
}


def _na(value, fmt: str = "{}") -> str:
    return "N/A" if value is None else fmt.format(value)


def render_source_banner(source: str) -> None:
    if source == SOURCE_MOCK:
        st.warning(
            "**MOCK DATA.** This is example output from the built-in demo, not from an AI model. "
            "It is not a research finding."
        )
    elif source == SOURCE_BACKEND:
        st.info("**Source: real backend.** This result came from the connected simplification backend.")


def render_summary_badges(entry: dict) -> None:
    source = (
        badge("MOCK DATA", "warn") if entry["source"] == SOURCE_MOCK else badge("REAL BACKEND", "info")
    )
    attempts = "N/A" if entry["attempts"] is None else str(entry["attempts"])
    badge_row(
        [
            source,
            badge(f"Level: {entry['level']}", "neutral"),
            status_badge(entry["verification_status"]),
            badge(f"Attempts: {attempts}", "neutral"),
        ]
    )


def render_changes(entry: dict) -> None:
    """Optional word-level view of what the rewrite changed."""
    if not entry["simplified_text"].strip():
        return
    with st.expander("Show what changed, word by word"):
        st.caption(
            "Struck-through words were removed from the original. Underlined words were added in the simplified text."
        )
        left_html, right_html = word_diff_html(entry["original_text"], entry["simplified_text"])
        left, right = st.columns(2)
        left.markdown("**Original**")
        left.markdown(f'<div class="diff-box">{left_html}</div>', unsafe_allow_html=True)
        right.markdown("**Simplified**")
        right.markdown(f'<div class="diff-box">{right_html}</div>', unsafe_allow_html=True)


def render_errors(entry: dict) -> None:
    for error in entry["errors"]:
        st.error(f"**{error['code']}**: {error['message']}")


def render_comparison(entry: dict) -> None:
    left, right = st.columns(2)
    with left:
        st.markdown("##### Original text")
        text_box(entry["original_text"])
    with right:
        st.markdown(f"##### Simplified text ({entry['level']})")
        if entry["simplified_text"].strip():
            text_box(entry["simplified_text"])
        else:
            st.info("No simplified text was produced for this run.")


def render_verification(entry: dict) -> None:
    st.markdown("### Verification")
    status = entry["verification_status"]
    if status == "PASS":
        st.success(
            "**Verification: PASS.** Every check that ran reported a pass. "
            "This checks that the text stays faithful to the original, not how simple it is. "
            "Automated checks can still miss problems, so please read the text yourself."
        )
    elif status == "FAIL":
        st.error("**Verification: FAIL.** At least one check found a problem. Review the details before using this text.")
    else:
        st.warning(
            "**Verification: NOT RUN.** No verification result is available for this run, "
            "so nothing is confirmed about the accuracy of the simplified text."
        )
    if entry["verification_details"]:
        st.table(
            [
                {"Check": d["check"], "Result": d["status"], "Explanation": d["explanation"]}
                for d in entry["verification_details"]
            ]
        )
    else:
        st.caption("No individual check details were provided.")
    if entry["source"] == SOURCE_MOCK:
        st.caption("These verification results are simulated by the demo.")


def render_metrics(entry: dict) -> None:
    metrics = entry["metrics"]
    st.markdown("### Metrics")
    top = st.columns(3)
    top[0].metric("Readability score", _na(metrics["readability_score"], "{:.1f}"))
    top[1].metric("Semantic similarity", _na(metrics["semantic_similarity"], "{:.2f}"))
    top[2].metric("Attempts", _na(entry["attempts"]))
    bottom = st.columns(3)
    bottom[0].metric("Words (original)", _na(metrics["word_count_original"], "{:,}"))
    bottom[1].metric("Words (simplified)", _na(metrics["word_count_simplified"], "{:,}"))

    original, simplified = metrics["word_count_original"], metrics["word_count_simplified"]
    if original and simplified is not None:
        change = (simplified - original) / original * 100
        direction = "shorter" if change < 0 else "longer" if change > 0 else "the same length"
        suffix = "" if change == 0 else f" ({abs(change):.0f}% {direction})"
        st.caption(f"The simplified text has {simplified:,} words versus {original:,} in the original{suffix}.")
    else:
        st.caption("A word-count comparison is not available for this run.")

    with st.expander("How to read these numbers"):
        if entry["source"] == SOURCE_MOCK:
            st.markdown(
                "- **Readability score:** in the demo this imitates a Flesch Reading Ease style score "
                "(higher = easier to read). The real formula is defined by the backend.\n"
                "- **Semantic similarity:** shown on a 0 to 1 scale (1 = very close in meaning). "
                "The real scale must be confirmed with the backend team.\n"
                "- All demo numbers are invented examples."
            )
        else:
            st.markdown(
                "- **Readability score:** Flesch Reading Ease of the simplified text, as described in the "
                "backend documentation. Higher means easier: roughly 60 is plain English and 30 or below is "
                "very difficult. Long technical words keep the score low even in a simple sentence, so compare "
                "it with the original text's score before drawing conclusions.\n"
                "- **Semantic similarity:** 0 to 1, calculated as (cosine similarity + 1) / 2, so values tend "
                "to look high. A score near 1 can also mean the text barely changed."
            )
        st.markdown(
            "- Semantic similarity shows how close the meaning of two texts is. "
            "It does **not** prove the simplified text is factually correct.\n"
            "- A readability score alone does **not** prove that a learner will understand the text.\n"
            "- **N/A** means the value was not provided. It does not mean zero."
        )


def render_downloads(entry: dict, key_prefix: str) -> None:
    st.markdown("### Download")
    left, right, _ = st.columns([1.2, 1.2, 1])
    with left:
        st.download_button(
            "Download as TXT",
            data=to_txt(entry),
            file_name=export_filename(entry, "txt"),
            mime="text/plain",
            key=f"{key_prefix}_txt_{entry['id']}",
        )
    with right:
        st.download_button(
            "Download as JSON",
            data=to_json(entry),
            file_name=export_filename(entry, "json"),
            mime="application/json",
            key=f"{key_prefix}_json_{entry['id']}",
        )


def render_result(entry: dict, view: str = "current") -> None:
    """Show one complete result. ``view`` keeps widget keys unique across tabs."""
    entry = {**entry, "_view": view}
    render_source_banner(entry["source"])
    render_summary_badges(entry)
    render_errors(entry)
    if entry["warnings"]:
        with st.expander(f"Notes about this response ({len(entry['warnings'])})"):
            for warning in entry["warnings"]:
                st.markdown(f"- {warning}")
    render_comparison(entry)
    render_changes(entry)
    render_verification(entry)
    render_metrics(entry)
    render_downloads(entry, view)


def entry_label(entry: dict) -> str:
    try:
        when = datetime.fromisoformat(entry["created_at"]).strftime("%H:%M:%S")
    except (KeyError, ValueError, TypeError):
        when = "?"
    source = "MOCK" if entry["source"] == SOURCE_MOCK else "BACKEND"
    return f"#{entry['id']} | {when} | {entry['level']} | {source} | {entry['verification_status']}"


def render_readability_chart(entries: list[dict]) -> None:
    """Bar chart of the readability score of each run that has one (oldest on the left)."""
    rows = [
        {"Run": f"#{e['id']} {e['level']} ({'mock' if e['source'] == SOURCE_MOCK else 'backend'})",
         "Readability score": e["metrics"]["readability_score"]}
        for e in reversed(entries)
        if e["metrics"]["readability_score"] is not None
    ]
    if len(rows) < 2:
        return
    st.markdown("#### Readability by run")
    st.bar_chart(pd.DataFrame(rows).set_index("Run"), y="Readability score")
    st.caption(
        "Flesch Reading Ease: higher means easier to read. Runs marked mock use invented example numbers."
    )


def render_history(entries: list[dict], on_clear) -> None:
    if not entries:
        st.info("No results yet. Run a simplification on the Simplify tab and it will appear here.")
        return
    st.caption("Results are kept only while this browser session is open. Download anything you want to keep.")
    st.table(
        [
            {
                "Run": f"#{e['id']}",
                "Time": entry_label(e).split(" | ")[1],
                "Level": e["level"],
                "Source": "Mock" if e["source"] == SOURCE_MOCK else "Backend",
                "Verification": e["verification_status"],
                "Words (simplified)": _na(e["metrics"]["word_count_simplified"]),
                "Errors": len(e["errors"]),
            }
            for e in entries
        ]
    )
    render_readability_chart(entries)
    by_label = {entry_label(e): e for e in entries}
    chosen = st.selectbox("Open a previous result", list(by_label), key="history_select")
    left, right, _ = st.columns([1, 1, 2])
    with left:
        st.download_button(
            "Download all as JSON",
            data=history_to_json(entries),
            file_name="simplification_history.json",
            mime="application/json",
            key="history_all_json",
        )
    with right:
        st.button("Clear history", on_click=on_clear, key="history_clear")
    st.divider()
    render_result(by_label[chosen], view="history")
