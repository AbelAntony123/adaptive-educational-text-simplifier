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
from services.env_file import load_env_file
from services.file_parser import SUPPORTED_EXTENSIONS, FileParseError, parse_uploaded_file
from services.mock_data import MOCK_SCENARIOS, SAMPLE_TEXT
from ui.components import LEVEL_HELP, render_history, render_result
from ui.history import add_entry, clear_history, get_entries, init_history
from ui.theme import apply_theme, hero, hint, step_heading

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


def render_sidebar() -> tuple[str, str, bool, bool]:
    use_cache = fallback = False
    env_names = load_env_file()  # reads a local .env file if there is one; only names are ever shown
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
            use_cache = st.toggle(
                "Reuse saved results",
                value=True,
                key="use_cache",
                help="The same text and level reuses an earlier verified result, so no new API requests are made.",
            )
            fallback = st.toggle(
                "Show demo data if the quota runs out",
                value=True,
                key="use_fallback",
                help="Only when Gemini's quota stops a run before any text exists. Always clearly labelled as demo data.",
            )
            st.caption(f"Saved results this session: {len(st.session_state['result_cache'])}")
            if env_names:
                st.caption("Settings found in .env: " + ", ".join(env_names))
            else:
                st.caption("No settings found in a .env file. Set them in the terminal or create .env from .env.example.")
        st.divider()
        st.markdown(
            "**About**\n\n"
            "This tool rewrites educational text at three difficulty levels and shows "
            "how the result was checked. Always read the output before using it."
        )
    return mode, scenario, use_cache, fallback


def render_input_panel() -> tuple[str, str | None, bool]:
    with st.container(border=True):
        step_heading(1, "Your text")
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
            height=200,
            placeholder="Paste or type the text you want to simplify...",
        )
        text = st.session_state["input_text"]
        info_col, sample_col = st.columns([3, 2])
        info_col.caption(f"{len(text):,} / {MAX_INPUT_CHARS:,} characters")
        sample_col.button("Use sample text", on_click=_use_sample)

    with st.container(border=True):
        step_heading(2, "Difficulty level")
        level = st.segmented_control(
            "Difficulty level",
            LEVELS,
            default=LEVELS[0],
            key="level",
            label_visibility="collapsed",
        )
        hint(LEVEL_HELP.get(level, "Choose a level to continue."))
        clicked = st.button("Simplify text", type="primary", key="simplify_button")
    return text, level, clicked


def main() -> None:
    st.set_page_config(page_title="Text Simplifier", layout="wide")
    st.session_state.setdefault("input_text", "")
    st.session_state.setdefault("upload_error", None)
    st.session_state.setdefault("current_entry", None)
    st.session_state.setdefault("result_cache", {})
    init_history(st.session_state)

    apply_theme()
    mode, scenario, use_cache, fallback = render_sidebar()

    hero(
        "Adaptive Educational Text Simplifier",
        "Paste a passage, pick a level, and compare. Every result shows how it was checked, "
        "and anything that was not checked says so.",
        highlight="Text Simplifier",
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
                    result = simplify(
                        text,
                        level,
                        mode=mode,
                        scenario=scenario,
                        cache=st.session_state["result_cache"] if use_cache else None,
                        fallback_to_mock=fallback,
                    )
                st.session_state["current_entry"] = add_entry(st.session_state, result)
                st.rerun()
        current = st.session_state["current_entry"]
        step_heading(3, "Results")
        if current is None:
            st.info("Your result will appear here after you click **Simplify text**.")
        else:
            render_result(current, view="current")

    with history_tab:
        render_history(entries, on_clear=_clear_history)


main()
