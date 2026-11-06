"""Smoke checks for the Streamlit attendance wizard without a running server."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


def _load_page(monkeypatch, step=1):
    state = {
        "att_step": step,
        "att_course_id": 7,
        "att_session_id": 19,
        "att_recognition": {"unknown_faces_count": 1},
        "att_checklist": {
            2: {"student_id": 2, "student_code": "BUC02", "full_name": "Mona Ali", "status": "present", "confidence": 0.91, "source": "auto"},
            3: {"student_id": 3, "student_code": "BUC03", "full_name": "Omar Samy", "status": "absent", "confidence": None, "source": "manual"},
        },
        "att_saved_records": [],
    }
    streamlit = MagicMock()
    streamlit.session_state = state
    def make_columns(spec):
        columns = [MagicMock() for _ in spec]
        for column in columns:
            column.__enter__.return_value = column
        return columns
    streamlit.columns.side_effect = make_columns
    streamlit.tabs.return_value = [MagicMock(), MagicMock()]
    for tab in streamlit.tabs.return_value:
        tab.__enter__.return_value = tab
    ui = MagicMock()
    ui.COLOR_TEXT_MUTED = "#5E6878"
    ui.COLOR_TEXT_PRIMARY = "#14213D"
    ui.COLOR_BORDER = "#E4DFD3"
    ui.confidence_bar_html.return_value = "confidence-bar"
    api = MagicMock()
    api.is_authenticated.return_value = True
    api.get_current_user.return_value = {"full_name": "Lecturer"}
    api.list_courses.return_value = [{"id": 7, "code": "CS101", "name": "Introduction to Computing"}]
    api.list_sessions.return_value = [{"id": 19, "status": "open"}]
    streamlit.selectbox.return_value = api.list_courses.return_value[0]
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    monkeypatch.setitem(sys.modules, "ui", ui)
    client_module = MagicMock()
    client_module.api = api
    client_module.ApiError = type("ApiError", (Exception,), {"message": "API error"})
    monkeypatch.setitem(sys.modules, "api_client", client_module)
    spec = importlib.util.spec_from_file_location("take_attendance_page", FRONTEND / "pages" / "5_Take_Attendance.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, streamlit, ui, api, state


def test_take_attendance_page_imports_and_renders_photo_step(monkeypatch):
    _, streamlit, ui, api, state = _load_page(monkeypatch)

    ui.inject_custom_css.assert_called_once()
    ui.page_header.assert_called_once_with(
        "Take Attendance", caption="Select course and provide classroom photos", badge="ATTENDANCE"
    )
    ui.step_wizard.assert_called_once_with(current_step=1)
    api.list_sessions.assert_called_once_with(7)
    streamlit.selectbox.assert_called_once()
    streamlit.file_uploader.assert_called_once()
    streamlit.camera_input.assert_called_once()
    assert state["att_course_id"] == 7


def test_review_step_renders_kpis_checklist_and_confidence(monkeypatch):
    module, streamlit, ui, _, _ = _load_page(monkeypatch, step=2)

    ui.step_wizard.assert_called_once_with(current_step=2)
    ui.metric_cards.assert_called_once_with([
        ("Recognized", "1 of roster"),
        ("Not found", "1 students"),
        ("Unknown faces", "1 in photos"),
    ])
    assert streamlit.checkbox.call_count == 2
    ui.confidence_bar_html.assert_called_once_with(91.0)
    assert callable(module._done_step)

