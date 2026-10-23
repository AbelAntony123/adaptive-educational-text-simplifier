"""Reusable Streamlit pieces: banners, results, verification, metrics, history."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from services.backend_adapter import SOURCE_BACKEND, SOURCE_MOCK
from ui.exports import export_filename, history_to_json, to_json, to_txt

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


def render_errors(entry: dict) -> None:
    for error in entry["errors"]:
        st.error(f"**{error['code']}**: {error['message']}")


def render_comparison(entry: dict) -> None:
    left, right = st.columns(2)
    with left:
        st.markdown("##### Original text")
        st.text_area(
            "Original text",
            value=entry["original_text"],
            height=300,
            disabled=True,
            label_visibility="collapsed",
            key=f"orig_{entry['id']}_{entry.get('_view', '')}",
        )
    with right:
        st.markdown(f"##### Simplified text ({entry['level']})")
        if entry["simplified_text"].strip():
            st.text_area(
                "Simplified text",
                value=entry["simplified_text"],
                height=300,
                disabled=True,
                label_visibility="collapsed",
                key=f"simp_{entry['id']}_{entry.get('_view', '')}",
            )
        else:
            st.info("No simplified text was produced for this run.")


def render_verification(entry: dict) -> None:
    st.markdown("### Verification")
    status = entry["verification_status"]
    if status == "PASS":
        st.success(
            "**Verification: PASS.** Every check that ran reported a pass. "
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
    cols = st.columns(5)
    cols[0].metric("Readability score", _na(metrics["readability_score"], "{:.1f}"))
    cols[1].metric("Semantic similarity", _na(metrics["semantic_similarity"], "{:.2f}"))
    cols[2].metric("Words (original)", _na(metrics["word_count_original"], "{:,}"))
    cols[3].metric("Words (simplified)", _na(metrics["word_count_simplified"], "{:,}"))
    cols[4].metric("Attempts", _na(entry["attempts"]))

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
                "- **Readability score:** the formula, scale and direction are defined by the backend. "
                "Confirm them with the backend team before comparing scores.\n"
                "- **Semantic similarity:** the scale is defined by the backend; this app does not rescale it."
            )
        st.markdown(
            "- Semantic similarity shows how close the meaning of two texts is. "
            "It does **not** prove the simplified text is factually correct.\n"
            "- A readability score alone does **not** prove that a learner will understand the text.\n"
            "- **N/A** means the value was not provided. It does not mean zero."
        )


def render_downloads(entry: dict, key_prefix: str) -> None:
    st.markdown("### Download")
    left, right, _ = st.columns([1, 1, 2])
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
    render_errors(entry)
    if entry["warnings"]:
        with st.expander(f"Notes about this response ({len(entry['warnings'])})"):
            for warning in entry["warnings"]:
                st.markdown(f"- {warning}")
    render_comparison(entry)
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
