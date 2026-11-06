"""Smoke checks for the admin Streamlit pages without a running server."""

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
    streamlit.dialog.side_effect = lambda _title: lambda function: function
    streamlit.tabs.side_effect = lambda labels: [_Context() for _ in labels]
    streamlit.columns.side_effect = lambda spec: [_Context() for _ in (range(spec) if isinstance(spec, int) else spec)]
    streamlit.text_input.return_value = ""
    streamlit.form.return_value = _Context()

    student = {
        "id": 1,
        "student_code": "20210042",
        "full_name": "Mona Ali",
        "level": "Level 2",
        "group_name": "Group A",
        "enrolled_faces_count": 1,
    }
    course = {"id": 7, "code": "CS101", "name": "Computer Vision", "lecturer_id": 3, "lecturer_name": "Dr. Ali", "student_count": 1}
    streamlit.selectbox.side_effect = lambda _label, options, **_kwargs: options[0]
    ui = MagicMock()
    api = MagicMock()
    api.is_authenticated.return_value = True
    api.get_current_user.return_value = {"full_name": "Administrator", "role": "admin"}
    api.list_students.return_value = [student]
    api.list_courses.return_value = [course]
    api.get_course_students.return_value = [student]

    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    monkeypatch.setitem(sys.modules, "ui", ui)
    client = MagicMock()
    client.api = api
    monkeypatch.setitem(sys.modules, "api_client", client)

    spec = importlib.util.spec_from_file_location(f"admin_page_{filename[0]}", FRONTEND / "pages" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, streamlit, ui, api


def test_students_page_imports_and_renders(monkeypatch):
    _, streamlit, ui, api = _load_page(monkeypatch, "2_Students.py")
    ui.inject_custom_css.assert_called_once()
    ui.page_header.assert_called_once_with(
        "Students",
        caption="Student directory, biometric consent status, and registration",
        badge="MANAGE",
    )
    api.list_students.assert_called_once_with(search=None)
    assert streamlit.tabs.called
    assert streamlit.form.called


def test_enroll_faces_page_imports_and_renders(monkeypatch):
    _, streamlit, ui, api = _load_page(monkeypatch, "3_Enroll_Faces.py")
    ui.inject_custom_css.assert_called_once()
    ui.page_header.assert_called_once_with(
        "Enroll Faces",
        caption="Capture 3 face poses (Front, Left, Right) with biometric quality checks",
        badge="MANAGE",
    )
    api.list_students.assert_called_once_with()
    assert streamlit.camera_input.call_count == 3
    assert streamlit.file_uploader.call_count == 3


def test_courses_page_imports_and_renders(monkeypatch):
    _, streamlit, ui, api = _load_page(monkeypatch, "4_Courses.py")
    ui.inject_custom_css.assert_called_once()
    ui.page_header.assert_called_once_with(
        "Courses & Rosters",
        caption="Create courses, assign lecturers, and configure student rosters",
        badge="MANAGE",
    )
    assert api.list_courses.call_count == 2
    api.get_course_students.assert_called_once_with(7)
    assert streamlit.multiselect.called
