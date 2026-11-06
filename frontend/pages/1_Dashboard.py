"""Lecturer overview with course and session health."""

import streamlit as st
import ui
from api_client import ApiError, api


ui.inject_custom_css()
if not api.is_authenticated():
    st.warning("Please sign in from the Home page.")
    st.stop()
user = api.get_current_user() or {}
ui.page_header(
    f"Welcome, {user.get('full_name', 'Lecturer')}",
    caption="Lecture overview, active courses, and attendance health",
    badge="ATTENDANCE",
)

try:
    courses = api.list_courses()
    open_sessions = 0
    for course in courses:
        sessions = api.list_sessions(course["id"])
        if any(session.get("status") == "open" for session in sessions):
            open_sessions += 1
except ApiError as exc:
    ui.show_error(getattr(exc, "message", str(exc)))
    courses = []
    open_sessions = 0

total_courses = len(courses)
total_students = sum(course.get("student_count", 0) for course in courses)
ui.metric_cards([
    ("My Courses", str(total_courses)),
    ("Open Sessions", str(open_sessions)),
    ("Total Enrolled Students", str(total_students)),
])

st.markdown("### Quick Actions")
col1, col2 = st.columns([1.5, 4])
with col1:
    if st.button("🚀 Take Attendance Now", type="primary", use_container_width=True):
        st.switch_page("pages/5_Take_Attendance.py")
with col2:
    if st.button("📊 View Full Reports", use_container_width=True):
        st.switch_page("pages/6_Reports.py")

st.markdown("### Active Courses")
if courses:
    rows = [
        {
            "Code": course.get("code", ""),
            "Name": course.get("name", ""),
            "Enrolled Students": course.get("student_count", 0),
        }
        for course in courses
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.info("No courses assigned yet. Contact your department administrator.")
