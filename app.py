"""Streamlit front end for the Adaptive Educational Text Simplifier.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from services.backend_adapter import (
    LEVELS,
    MAX_INPUT_CHARS,
    SOURCE_BACKEND,
    SOURCE_MOCK,
    simplify,
    validate_input,
)
from services.file_parser import SUPPORTED_EXTENSIONS, FileParseError, parse_uploaded_file
from services.mock_data import MOCK_SCENARIOS, SAMPLE_TEXT
from ui.components import LEVEL_HELP, render_history, render_result
from ui.history import add_entry, clear_history, get_entries, init_history

MODE_MOCK = "Demo with mock data"
MODE_BACKEND = "Real backend"


def _use_sample() -> None:
    st.session_state["input_text"] = SAMPLE_TEXT
    st.session_state["upload_error"] = None


def _load_upload() -> None:
    """Runs when the uploaded file changes: copy its text into the text box."""
    st.session_state["upload_error"] = None
    uploaded = st.session_state.get("uploader")
    if uploaded is None:
        return
    try:
        st.session_state["input_text"] = parse_uploaded_file(uploaded.name, uploaded.getvalue())
    except FileParseError as exc:
        st.session_state["upload_error"] = str(exc)


def _clear_history() -> None:
    clear_history(st.session_state)
    st.session_state["current_entry"] = None


def render_sidebar() -> tuple[str, str]:
    with st.sidebar:
        st.header("Settings")
        mode_label = st.radio("Data source", [MODE_MOCK, MODE_BACKEND], key="mode")
        mode = SOURCE_MOCK if mode_label == MODE_MOCK else SOURCE_BACKEND
        scenario = "success"
        if mode == SOURCE_MOCK:
            st.caption("Mock data is invented example output used to test the interface.")
            scenario_label = st.selectbox("Demo scenario", list(MOCK_SCENARIOS), key="scenario")
            scenario = MOCK_SCENARIOS[scenario_label]
        else:
            st.caption("Uses the simplification backend if it has been connected.")
        st.divider()
        st.markdown(
            "**About**\n\n"
            "This tool rewrites educational text at three difficulty levels and shows "
            "how the result was checked. Always read the output before using it."
        )
    return mode, scenario


def render_input_panel() -> tuple[str, str, bool]:
    st.subheader("1. Enter your text")
    st.file_uploader(
        f"Upload a file (optional): {', '.join(SUPPORTED_EXTENSIONS)}",
        type=[ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS],
        key="uploader",
        on_change=_load_upload,
    )
    if st.session_state.get("upload_error"):
        st.error(st.session_state["upload_error"])
    st.text_area(
        "Educational text",
        key="input_text",
        height=220,
        placeholder="Paste or type the text you want to simplify...",
    )
    text = st.session_state["input_text"]
    info_col, sample_col = st.columns([3, 1])
    info_col.caption(f"{len(text):,} / {MAX_INPUT_CHARS:,} characters")
    sample_col.button("Use sample text", on_click=_use_sample)

    st.subheader("2. Choose a difficulty level")
    level = st.radio(
        "Difficulty level",
        LEVELS,
        key="level",
        horizontal=True,
        captions=[LEVEL_HELP[name] for name in LEVELS],
        label_visibility="collapsed",
    )
    clicked = st.button("Simplify text", type="primary", key="simplify_button")
    return text, level, clicked


def main() -> None:
    st.set_page_config(page_title="Text Simplifier", layout="wide")
    st.session_state.setdefault("input_text", "")
    st.session_state.setdefault("upload_error", None)
    st.session_state.setdefault("current_entry", None)
    init_history(st.session_state)

    mode, scenario = render_sidebar()

    st.title("Adaptive Educational Text Simplifier")
    st.write(
        "Rewrite educational text at the Beginner, Intermediate or Advanced level, "
        "then compare it with the original, see how it was checked, and download the result."
    )

    entries = get_entries(st.session_state)
    simplify_tab, history_tab = st.tabs(["Simplify", f"History ({len(entries)})"])

    with simplify_tab:
        text, level, clicked = render_input_panel()
        if clicked:
            problems = validate_input(text, level)
            if problems:
                for problem in problems:
                    st.error(problem)
            else:
                label = "demo (mock data)" if mode == SOURCE_MOCK else "backend"
                with st.spinner(f"Simplifying at the {level} level using the {label}..."):
                    result = simplify(text, level, mode=mode, scenario=scenario)
                st.session_state["current_entry"] = add_entry(st.session_state, result)
                st.rerun()
        current = st.session_state["current_entry"]
        st.divider()
        st.subheader("3. Results")
        if current is None:
            st.info("Your result will appear here after you click **Simplify text**.")
        else:
            render_result(current, view="current")

    with history_tab:
        render_history(entries, on_clear=_clear_history)


main()
