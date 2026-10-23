"""Page styling and small HTML helpers. Status is always shown as text, never by colour alone."""

from __future__ import annotations

import html

import streamlit as st

_CSS = """
<style>
.block-container { max-width: 1200px; padding-top: 2rem; }
h1 { color: #1F4E79; letter-spacing: -0.01em; }
h2, h3, h4 { color: #1A2433; }
.accent-bar { height: 4px; width: 72px; border-radius: 2px; background: #1F4E79; margin: -0.4rem 0 1rem 0; }
.badge-row { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0.25rem 0 0.75rem 0; }
.badge { display: inline-block; padding: 0.15rem 0.7rem; border-radius: 999px; font-weight: 600;
         font-size: 0.85rem; border: 1px solid; white-space: nowrap; }
.badge-pass { background: #E6F4EA; color: #14532D; border-color: #14532D; }
.badge-fail { background: #FDECEA; color: #7A1410; border-color: #7A1410; }
.badge-warn { background: #FFF4D6; color: #6B4500; border-color: #6B4500; }
.badge-info { background: #E3EEF9; color: #123B63; border-color: #123B63; }
.badge-neutral { background: #EEF1F5; color: #1A2433; border-color: #5B6675; }
.text-box { border: 1px solid #C9D3DF; border-radius: 8px; padding: 0.75rem 1rem; background: #FFFFFF;
            color: #1A2433; line-height: 1.6; white-space: pre-wrap; min-height: 12rem; max-height: 22rem;
            overflow-y: auto; }
.diff-box { border: 1px solid #C9D3DF; border-radius: 8px; padding: 0.75rem 1rem; background: #FFFFFF;
            line-height: 1.7; }
.diff-box del { background: #FDECEA; color: #7A1410; text-decoration: line-through; padding: 0 2px; }
.diff-box ins { background: #E6F4EA; color: #14532D; text-decoration: underline; padding: 0 2px; }
div[data-testid="stDownloadButton"] button { white-space: nowrap; }
@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; }
  h1 { font-size: 1.6rem; }
}
div[data-testid="stMetric"] { background: #F2F6FA; border: 1px solid #D7E0EA; border-radius: 10px;
                              padding: 0.6rem 0.9rem; }
</style>
"""

_STATUS_KINDS = {"PASS": "pass", "FAIL": "fail", "NOT RUN": "warn"}


def apply_theme() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown('<div class="accent-bar"></div>', unsafe_allow_html=True)


def badge(label: str, kind: str = "neutral") -> str:
    return f'<span class="badge badge-{kind}">{html.escape(label)}</span>'


def status_badge(status: str) -> str:
    return badge(f"Verification: {status}", _STATUS_KINDS.get(status, "warn"))


def text_box(text: str) -> None:
    """Readable, high-contrast, scrollable display of plain text (HTML-escaped)."""
    st.markdown(f'<div class="text-box">{html.escape(text)}</div>', unsafe_allow_html=True)


def badge_row(badges: list[str]) -> None:
    st.markdown(f'<div class="badge-row">{"".join(badges)}</div>', unsafe_allow_html=True)
