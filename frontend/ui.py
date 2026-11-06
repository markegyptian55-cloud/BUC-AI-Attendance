"""Shared visual tokens and Streamlit components for Attendance AI."""

from html import escape
from typing import List, Optional, Tuple

import streamlit as st

COLOR_BG = "#F7F5EF"
COLOR_CARD_BG = "#FFFDF8"
COLOR_SIDEBAR_BG = "#EDE7DA"
COLOR_BORDER = "#E4DFD3"
COLOR_BORDER_DARK = "#D8D1C3"
COLOR_TEXT_PRIMARY = "#14213D"
COLOR_TEXT_BODY = "#3E4A5C"
COLOR_TEXT_MUTED = "#5E6878"
COLOR_PRIMARY = "#B5570B"
COLOR_PRIMARY_HOVER = "#994606"
COLOR_AMBER = "#F29B4A"
COLOR_BLUE = "#2563A8"
COLOR_TRACK = "#E4DFD3"


def inject_custom_css() -> None:
    """Apply the shared desktop-app theme to Streamlit's page chrome."""
    st.markdown(
        f"""<style>
        :root {{
          --buc-bg: {COLOR_BG}; --buc-card: {COLOR_CARD_BG};
          --buc-sidebar: {COLOR_SIDEBAR_BG}; --buc-border: {COLOR_BORDER};
          --buc-border-dark: {COLOR_BORDER_DARK}; --buc-text: {COLOR_TEXT_PRIMARY};
          --buc-body: {COLOR_TEXT_BODY}; --buc-muted: {COLOR_TEXT_MUTED};
          --buc-primary: {COLOR_PRIMARY}; --buc-primary-hover: {COLOR_PRIMARY_HOVER};
          --buc-amber: {COLOR_AMBER}; --buc-blue: {COLOR_BLUE}; --buc-track: {COLOR_TRACK};
        }}
        html, body, [data-testid="stAppViewContainer"] {{ background: var(--buc-bg); color: var(--buc-text); }}
        [data-testid="stSidebar"] {{ background: var(--buc-sidebar); border-right: 1px solid var(--buc-border-dark); }}
        [data-testid="stSidebar"] * {{ color: var(--buc-body); }}
        [data-testid="stHeader"], #MainMenu, footer {{ visibility: hidden; height: 0; }}
        [data-testid="stToolbar"] {{ visibility: hidden; }}
        h1, h2, h3 {{ color: var(--buc-text); letter-spacing: -0.02em; }}
        p, label {{ color: var(--buc-body); }}
        div.stButton > button {{ border-radius: 8px; font-weight: 600; transition: background .15s ease, border-color .15s ease; }}
        div.stButton > button[kind="primary"] {{ background: var(--buc-primary); color: {COLOR_BG}; border: 1px solid var(--buc-primary); }}
        div.stButton > button[kind="primary"]:hover {{ background: var(--buc-primary-hover); border-color: var(--buc-primary-hover); color: {COLOR_BG}; }}
        div.stButton > button[kind="secondary"] {{ background: var(--buc-card); color: var(--buc-text); border: 1px solid var(--buc-border-dark); }}
        .metric-card {{ background: var(--buc-card); border: 1px solid var(--buc-border); border-radius: 14px; padding: 18px 20px; height: 100%; }}
        .metric-card-label {{ color: var(--buc-muted); font-size: .85rem; margin-bottom: 8px; }}
        .metric-card-value {{ color: var(--buc-text); font-weight: 700; font-size: 1.35rem; line-height: 1.25; }}
        .step-pill {{ display: inline-block; background: var(--buc-card); color: var(--buc-muted); border: 1px solid var(--buc-border); border-radius: 20px; padding: 4px 16px; font-size: .9rem; white-space: nowrap; }}
        .step-pill-active {{ display: inline-block; background: var(--buc-primary); color: {COLOR_BG}; font-weight: 700; border-radius: 20px; padding: 4px 16px; font-size: .9rem; white-space: nowrap; }}
        .review-table-header {{ background: var(--buc-sidebar); color: var(--buc-text); font-weight: 600; }}
        </style>""",
        unsafe_allow_html=True,
    )


def page_header(title: str, caption: Optional[str] = None, badge: Optional[str] = None) -> None:
    badge_html = (
        f'<div style="color:{COLOR_PRIMARY};font-size:.72rem;font-weight:700;letter-spacing:.12em;margin-bottom:8px">{escape(badge.upper())}</div>'
        if badge
        else ""
    )
    caption_html = (
        f'<div style="color:{COLOR_TEXT_MUTED};font-size:1rem;margin-top:6px">{escape(caption)}</div>'
        if caption
        else ""
    )
    st.markdown(
        f'{badge_html}<h1 style="color:{COLOR_TEXT_PRIMARY};margin:0">{escape(title)}</h1>{caption_html}',
        unsafe_allow_html=True,
    )


def step_wizard(current_step: int, steps: Optional[List[str]] = None) -> None:
    labels = steps if steps is not None else ["1 · Photos", "2 · Review", "3 · Done"]
    pills = []
    for index, label in enumerate(labels, start=1):
        css_class = "step-pill-active" if index == current_step else "step-pill"
        pills.append(f'<span class="{css_class}">{escape(str(label))}</span>')
    st.markdown(
        '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:18px 0">'
        + "".join(pills)
        + "</div>",
        unsafe_allow_html=True,
    )


def metric_cards(metrics: List[Tuple[str, str]]) -> None:
    columns = st.columns(len(metrics)) if metrics else []
    for column, (label, value) in zip(columns, metrics):
        with column:
            st.markdown(
                '<div class="metric-card">'
                f'<div class="metric-card-label">{escape(str(label))}</div>'
                f'<div class="metric-card-value">{escape(str(value))}</div>'
                "</div>",
                unsafe_allow_html=True,
            )


def confidence_bar_html(confidence: float) -> str:
    """Return a safe, clamped confidence meter as embeddable HTML."""
    percentage = max(0.0, min(100.0, float(confidence)))
    label = f"{percentage:.0f}%"
    return (
        '<div style="display:flex;align-items:center;gap:10px">'
        f'<div role="progressbar" aria-valuenow="{percentage:g}" aria-valuemin="0" aria-valuemax="100" '
        f'style="height:8px;flex:1;background:{COLOR_TRACK};border-radius:99px;overflow:hidden">'
        f'<div style="height:100%;width:{percentage:g}%;background:{COLOR_BLUE};border-radius:99px"></div></div>'
        f'<span style="color:{COLOR_TEXT_BODY};font-size:.85rem;font-weight:600">{label}</span></div>'
    )


def sidebar_profile(user_name: str, role: str) -> None:
    st.sidebar.markdown(
        f'<div style="border-top:1px solid {COLOR_BORDER_DARK};padding-top:14px;margin-top:18px">'
        f'<div style="color:{COLOR_TEXT_MUTED};font-size:.82rem">Signed in: {escape(role)}</div>'
        f'<div style="color:{COLOR_TEXT_PRIMARY};font-weight:700;margin-top:3px">{escape(user_name)}</div></div>',
        unsafe_allow_html=True,
    )


def show_error(message: str) -> None:
    st.error(message)


def show_success(message: str) -> None:
    st.toast(message, icon="✅")
