"""Smoke checks for the lecturer Streamlit pages without a running server."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _load_page(monkeypatch, filename):
    streamlit = MagicMock()
    streamlit.session_state = {}
    streamlit.columns.side_effect = lambda spec: [_Context() for _ in (range(spec) if isinstance(spec, int) else spec)]
    streamlit.selectbox.side_effect = lambda _label, options, **_kwargs: options[0]
    ui = MagicMock()
    api = MagicMock()
    api.is_authenticated.return_value = True
    api.get_current_user.return_value = {"full_name": "Dr. Lecturer", "role": "lecturer"}
    api.list_courses.return_value = [
        {"id": 7, "code": "CS101", "name": "Computer Vision", "student_count": 2}
    ]
    api.list_sessions.return_value = [{"id": 9, "status": "open"}]
    api.get_course_report.return_value = {
        "total_sessions": 2,
        "students": [
            {"student_code": "BUC01", "full_name": "Mona Ali", "attended_sessions": 2, "total_sessions": 2, "attendance_percentage": 100.0},
            {"student_code": "BUC02", "full_name": "Omar Samy", "attended_sessions": 1, "total_sessions": 2, "attendance_percentage": 50.0},
        ],
    }
    api.get_course_report_csv.return_value = b"\xef\xbb\xbfStudent Code\n"
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    monkeypatch.setitem(sys.modules, "ui", ui)
    client = MagicMock()
    client.api = api
    client.ApiError = type("ApiError", (Exception,), {"message": "API error"})
    monkeypatch.setitem(sys.modules, "api_client", client)
    spec = importlib.util.spec_from_file_location(f"lecturer_page_{filename[0]}", FRONTEND / "pages" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, streamlit, ui, api


def test_dashboard_imports_and_renders_metrics_and_courses(monkeypatch):
    _load_page(monkeypatch, "1_Dashboard.py")
    streamlit = sys.modules["streamlit"]
    ui = sys.modules["ui"]
    api = sys.modules["api_client"].api
    ui.inject_custom_css.assert_called_once()
    ui.page_header.assert_called_once_with(
        "Welcome, Dr. Lecturer",
        caption="Lecture overview, active courses, and attendance health",
        badge="ATTENDANCE",
    )
    ui.metric_cards.assert_called_once_with([
        ("My Courses", "1"), ("Open Sessions", "1"), ("Total Enrolled Students", "2")
    ])
    api.list_sessions.assert_called_once_with(7)
    assert streamlit.dataframe.called or any("CS101" in str(call) for call in streamlit.markdown.call_args_list)


def test_reports_imports_and_renders_metrics_table_and_csv_download(monkeypatch):
    _load_page(monkeypatch, "6_Reports.py")
    streamlit = sys.modules["streamlit"]
    ui = sys.modules["ui"]
    api = sys.modules["api_client"].api
    ui.inject_custom_css.assert_called_once()
    ui.metric_cards.assert_called_once_with([
        ("Completed Lectures", "2"), ("Enrolled Students", "2"), ("Average Attendance", "75.0%")
    ])
    api.get_course_report.assert_called_once_with(7)
    api.get_course_report_csv.assert_called_once_with(7)
    assert streamlit.download_button.called
    assert ui.confidence_bar_html.call_count == 2
    assert any("At Risk" in str(call) for call in streamlit.markdown.call_args_list)
