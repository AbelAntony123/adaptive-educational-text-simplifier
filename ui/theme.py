"""Page styling and small HTML helpers. Status is always shown as text, never by colour alone.

Palette: #202734 (base), #36415A (raised surfaces), #B7D894 (accent), #E0F8C7 (text).
Motion follows a few simple rules: strong ease-out curves, nothing slower than 300 ms, press
feedback on every button, hover effects only on real pointers, and no motion at all for people
who ask for reduced motion.
"""

from __future__ import annotations

import html

import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap');

:root {
  --ease-out: cubic-bezier(0.23, 1, 0.32, 1);
  --base: #202734;
  --sunken: #1A202B;
  --raised: #36415A;
  --card: #273043;
  --accent: #B7D894;
  --text: #E0F8C7;
  --muted: #A9B8A0;
  --line: rgba(224, 248, 199, 0.14);
  --shadow: 0 1px 0 rgba(224, 248, 199, 0.04) inset, 0 12px 30px -16px rgba(0, 0, 0, 0.55);
  --sans: 'Geist', system-ui, -apple-system, 'Segoe UI', sans-serif;
  --mono: 'Geist Mono', ui-monospace, 'Cascadia Code', Consolas, monospace;
}

.stApp { font-family: var(--sans); background: var(--base); color: var(--text); }
.stApp button, .stApp input, .stApp textarea { font-family: var(--sans); }
.block-container { max-width: 1120px; padding-top: 2rem; padding-bottom: 4rem; }
h2, h3, h4 { color: var(--text); letter-spacing: -0.015em; }
.stApp [data-testid="stCaptionContainer"], .stApp small { color: var(--muted); }

@keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

/* ---------- header ---------- */
.masthead { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 2.5rem; align-items: end;
            padding: 0.5rem 0 2rem 0; border-bottom: 1px solid var(--line); margin-bottom: 1.75rem;
            animation: rise 320ms var(--ease-out) both; }
.masthead .eyebrow { font-family: var(--mono); font-size: 0.74rem; letter-spacing: 0.12em; text-transform: uppercase;
                     color: var(--accent); font-weight: 500; }
.masthead h1 { font-family: var(--sans); font-weight: 600; font-size: 3rem; line-height: 1.04; letter-spacing: -0.04em;
               margin: 0.7rem 0 1rem 0; padding: 0; color: var(--text); text-wrap: balance; }
.masthead h1 .mark { color: var(--accent); }
.masthead p.lede { margin: 0; max-width: 31rem; font-size: 1.08rem; line-height: 1.6; color: var(--muted); text-wrap: pretty; }
.specimen { background: var(--raised); border: 1px solid var(--line); border-radius: 16px; padding: 1.1rem 1.25rem;
            box-shadow: var(--shadow); }
.specimen .label { font-family: var(--mono); font-size: 0.7rem; letter-spacing: 0.1em; text-transform: uppercase;
                   color: var(--accent); margin-bottom: 0.3rem; }
.specimen .line { font-size: 0.98rem; line-height: 1.55; color: var(--text); margin: 0 0 0.85rem 0; }
.specimen .line.before { color: var(--muted); text-decoration: line-through; text-decoration-color: rgba(224,248,199,0.35); }
.specimen .note { font-family: var(--mono); font-size: 0.7rem; color: var(--muted); margin: 0; }

/* ---------- cards ---------- */
div[data-testid="stVerticalBlockBorderWrapper"] { border: 1px solid var(--line) !important; border-radius: 16px;
        background: var(--card); box-shadow: var(--shadow); }
.step { display: flex; align-items: center; gap: 0.7rem; margin: 0.15rem 0 0.75rem 0; font-weight: 600;
        font-size: 1.08rem; color: var(--text); letter-spacing: -0.01em; }
.step-num { display: inline-grid; place-items: center; width: 1.7rem; height: 1.7rem; border-radius: 8px;
            background: var(--accent); color: var(--base); font-family: var(--mono); font-size: 0.8rem; font-weight: 600; }
.hint { color: var(--muted); font-size: 0.92rem; line-height: 1.5; margin: 0.45rem 0 0.95rem 0; }

/* ---------- controls ---------- */
.stApp button[data-testid="stBaseButton-primary"] {
  background: var(--accent); color: var(--base); border: none; border-radius: 12px;
  padding: 0.65rem 1.6rem; font-weight: 600; min-width: 11rem;
  transition: transform 160ms var(--ease-out), box-shadow 200ms var(--ease-out), filter 160ms var(--ease-out); }
.stApp button[data-testid="stBaseButton-primary"] p { color: var(--base); font-weight: 600; }
.stApp button[data-testid="stBaseButton-secondary"], div[data-testid="stDownloadButton"] button {
  border-radius: 10px; font-weight: 500; white-space: nowrap; border: 1px solid var(--line);
  background: var(--raised); color: var(--text);
  transition: transform 160ms var(--ease-out), border-color 160ms var(--ease-out), background-color 160ms var(--ease-out); }
.stApp button[data-testid="stBaseButton-primary"]:active,
.stApp button[data-testid="stBaseButton-secondary"]:active,
div[data-testid="stDownloadButton"] button:active { transform: scale(0.97); }
@media (hover: hover) and (pointer: fine) {
  .stApp button[data-testid="stBaseButton-primary"]:hover { filter: brightness(1.07);
        box-shadow: 0 10px 24px -12px rgba(183, 216, 148, 0.7); }
  .stApp button[data-testid="stBaseButton-secondary"]:hover, div[data-testid="stDownloadButton"] button:hover {
        border-color: var(--accent); background-color: #3F4B68; }
}
div[data-baseweb="textarea"], div[data-baseweb="select"] > div { border-radius: 12px;
        transition: box-shadow 160ms var(--ease-out), border-color 160ms var(--ease-out); }
div[data-baseweb="textarea"]:focus-within { box-shadow: 0 0 0 3px rgba(183, 216, 148, 0.3); }
section[data-testid="stSidebar"] { background: var(--sunken); border-right: 1px solid var(--line); }
div[data-testid="stAlert"] { border-radius: 12px; }
button[data-baseweb="tab"] { font-weight: 600; }
div[data-testid="stFileUploaderDropzone"] { border-radius: 12px; border: 1px dashed var(--line); background: var(--sunken); }

/* ---------- content ---------- */
.badge-row { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0.25rem 0 0.85rem 0; animation: rise 280ms var(--ease-out) both; }
.badge { display: inline-block; padding: 0.18rem 0.75rem; border-radius: 999px; font-weight: 600; font-size: 0.82rem;
         border: 1px solid; white-space: nowrap; }
.badge-pass { background: var(--accent); color: var(--base); border-color: var(--accent); }
.badge-fail { background: #4A2B30; color: #FFB4AB; border-color: #FFB4AB; }
.badge-warn { background: #4A3D1C; color: #F5D78A; border-color: #F5D78A; }
.badge-info { background: var(--raised); color: var(--text); border-color: var(--accent); }
.badge-neutral { background: var(--raised); color: var(--text); border-color: rgba(224, 248, 199, 0.3); }
.text-box { border: 1px solid var(--line); border-radius: 12px; padding: 0.9rem 1.1rem; background: var(--sunken);
            color: var(--text); font-family: var(--sans); font-size: 1rem; line-height: 1.7; white-space: pre-wrap;
            min-height: 12rem; max-height: 22rem; overflow-y: auto; animation: rise 280ms var(--ease-out) both; }
div[data-testid="stColumn"]:nth-child(2) .text-box { animation-delay: 50ms; }
.diff-box { border: 1px solid var(--line); border-radius: 12px; padding: 0.85rem 1.1rem; background: var(--sunken);
            font-family: var(--sans); line-height: 1.75; color: var(--text); }
.diff-box del { background: rgba(255, 180, 171, 0.16); color: #FFB4AB; text-decoration: line-through; padding: 0 2px; border-radius: 3px; }
.diff-box ins { background: rgba(183, 216, 148, 0.18); color: var(--accent); text-decoration: underline; padding: 0 2px; border-radius: 3px; }
div[data-testid="stMetric"] { background: var(--raised); border: 1px solid var(--line); border-radius: 14px;
                              padding: 0.8rem 1rem; box-shadow: var(--shadow); }
div[data-testid="stMetricValue"] { font-family: var(--sans); font-weight: 600; letter-spacing: -0.03em;
                                   font-variant-numeric: tabular-nums; color: var(--accent); }

@media (max-width: 820px) {
  .masthead { grid-template-columns: minmax(0, 1fr); gap: 1.5rem; }
  .masthead h1 { font-size: 2.2rem; }
}
@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; }
}
@media (prefers-reduced-motion: reduce) {
  .masthead, .badge-row, .text-box { animation: none; }
  .stApp button { transition: none; }
  .stApp button:active { transform: none; }
}
</style>
"""

_STATUS_KINDS = {"PASS": "pass", "FAIL": "fail", "NOT RUN": "warn"}


def apply_theme() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str, highlight: str = "") -> None:
    """Plain, left-aligned masthead with a small hand-written before/after illustration."""
    safe_title = html.escape(title)
    if highlight and highlight in title:
        safe_title = html.escape(title).replace(
            html.escape(highlight), f'<span class="mark">{html.escape(highlight)}</span>'
        )
    st.markdown(
        '<div class="masthead">'
        "<div>"
        '<div class="eyebrow">Research prototype</div>'
        f"<h1>{safe_title}</h1>"
        f'<p class="lede">{html.escape(subtitle)}</p>'
        "</div>"
        '<div class="specimen">'
        '<div class="label">Before</div>'
        '<p class="line before">Chlorophyll absorbs photons, driving the synthesis of ATP.</p>'
        '<div class="label">After (Beginner)</div>'
        '<p class="line">Chlorophyll catches light. The plant uses it to make energy.</p>'
        '<p class="note">Hand-written illustration, not model output.</p>'
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def step_heading(number: int, title: str) -> None:
    st.markdown(
        f'<div class="step"><span class="step-num">{number}</span>{html.escape(title)}</div>',
        unsafe_allow_html=True,
    )


def hint(text: str) -> None:
    st.markdown(f'<div class="hint">{html.escape(text)}</div>', unsafe_allow_html=True)


def badge(label: str, kind: str = "neutral") -> str:
    return f'<span class="badge badge-{kind}">{html.escape(label)}</span>'


def status_badge(status: str) -> str:
    return badge(f"Verification: {status}", _STATUS_KINDS.get(status, "warn"))


def text_box(text: str) -> None:
    """Readable, high-contrast, scrollable display of plain text (HTML-escaped)."""
    st.markdown(f'<div class="text-box">{html.escape(text)}</div>', unsafe_allow_html=True)


def badge_row(badges: list[str]) -> None:
    st.markdown(f'<div class="badge-row">{"".join(badges)}</div>', unsafe_allow_html=True)
