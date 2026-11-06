"""Smoke tests for the shared Streamlit UI components."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


def load_ui_module(monkeypatch):
    """Load ui.py with a lightweight Streamlit stub for non-rendering tests."""
    streamlit = MagicMock()
    columns = [MagicMock(), MagicMock(), MagicMock()]
    for column in columns:
        column.__enter__.return_value = column
    streamlit.columns.return_value = columns
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    spec = importlib.util.spec_from_file_location("attendance_frontend_ui", FRONTEND / "ui.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, streamlit, columns


def test_streamlit_theme_config_has_expected_brand_colors():
    config = (FRONTEND / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert 'primaryColor = "#B5570B"' in config
    assert 'backgroundColor = "#F7F5EF"' in config


def test_ui_module_imports_and_html_helpers_render(monkeypatch):
    ui, streamlit, columns = load_ui_module(monkeypatch)

    ui.step_wizard(2)
    wizard_html = streamlit.markdown.call_args.args[0]
    assert 'class="step-pill-active">2 · Review</span>' in wizard_html
    assert 'class="step-pill">1 · Photos</span>' in wizard_html

    confidence_html = ui.confidence_bar_html(91)
    assert 'width:91%' in confidence_html
    assert "91%" in confidence_html

    ui.metric_cards([("Recognized", "24 of roster"), ("Unknown faces", "1 in photos")])
    assert streamlit.columns.called
    # Streamlit routes st.markdown to the active column context; the simple
    # stub verifies the layout was created and both cards were rendered.
    assert streamlit.markdown.call_count == 3
    assert all("metric-card" in call.args[0] for call in streamlit.markdown.call_args_list[-2:])
    assert all(column.__enter__.called for column in columns[:2])

