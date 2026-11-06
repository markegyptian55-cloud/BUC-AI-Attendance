"""Course attendance report viewer and CSV export."""

import streamlit as st
import ui
from api_client import ApiError, api


def _course_label(course: dict) -> str:
    return f"{course.get('code', '')} · {course.get('name', '')}"


def _render_students(students: list[dict]) -> None:
    heading = st.columns([1.5, 3, 1.4, 3, 1.5])
    for column, label in zip(heading, ("Code", "Student", "Attended / Total", "Attendance", "Status")):
        with column:
            st.markdown(f"**{label}**")

    for student in students:
        percentage = float(student.get("attendance_percentage", 0.0) or 0.0)
        total = student.get("total_sessions", 0)
        attended = student.get("attended_sessions", 0)
        code, name, count, meter, status = st.columns([1.5, 3, 1.4, 3, 1.5])
        with code:
            st.markdown(str(student.get("student_code", "")))
        with name:
            st.markdown(str(student.get("full_name", "")))
        with count:
            st.markdown(f"{attended} / {total}")
        with meter:
            st.markdown(ui.confidence_bar_html(percentage), unsafe_allow_html=True)
        with status:
            if percentage < 75.0:
                st.markdown("⚠️ At Risk (< 75%)")
            else:
                st.markdown("✅ On Track")


ui.inject_custom_css()
if not api.is_authenticated():
    st.warning("Please sign in from the Home page.")
    st.stop()

ui.page_header(
    "Attendance Reports",
    caption="Review attendance percentages and export verified CSV rosters",
    badge="REPORTS",
)

try:
    courses = api.list_courses()
except ApiError as exc:
    ui.show_error(getattr(exc, "message", str(exc)))
    st.stop()

if not courses:
    st.info("No courses are available for attendance reporting yet.")
    st.stop()

selected_course = st.selectbox("Select Course", courses, format_func=_course_label)
try:
    report = api.get_course_report(selected_course["id"])
except ApiError as exc:
    ui.show_error(getattr(exc, "message", str(exc)))
    st.stop()

total_sessions = int(report.get("total_sessions", 0) or 0)
students = report.get("students", []) or []
if total_sessions == 0:
    st.info("No completed lecture sessions recorded yet for this course. Start an attendance session to record student presence.")
    if students:
        # The API supplies zero rates when no completed sessions exist.
        _render_students(students)
else:
    average = sum(float(student.get("attendance_percentage", 0.0) or 0.0) for student in students) / len(students) if students else 0.0
    ui.metric_cards([
        ("Completed Lectures", str(total_sessions)),
        ("Enrolled Students", str(len(students))),
        ("Average Attendance", f"{average:.1f}%"),
    ])
    try:
        csv_data = api.get_course_report_csv(selected_course["id"])
        st.download_button(
            "📥 Download Official Attendance Report (CSV)",
            data=csv_data,
            file_name=f"attendance_report_{selected_course['code']}.csv",
            mime="text/csv",
            type="primary",
        )
    except ApiError as exc:
        ui.show_error(getattr(exc, "message", str(exc)))
    _render_students(students)
