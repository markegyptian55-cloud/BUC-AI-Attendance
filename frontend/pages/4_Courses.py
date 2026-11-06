"""Admin course catalog and roster management."""

import streamlit as st
import ui
from api_client import api


ui.inject_custom_css()
user = api.get_current_user()
if not api.is_authenticated() or not user or user.get("role") != "admin":
    st.warning("Administrator access is required. Please sign in with an admin account.")
    st.stop()

ui.page_header(
    "Courses & Rosters",
    caption="Create courses, assign lecturers, and configure student rosters",
    badge="MANAGE",
)

catalog_tab, create_tab, roster_tab = st.tabs(["📚 Course Catalog", "➕ Create Course", "👥 Manage Roster"])

with catalog_tab:
    try:
        courses = api.list_courses()
    except Exception as exc:
        courses = []
        ui.show_error(str(getattr(exc, "message", exc)))
    if courses:
        st.dataframe([
            {
                "Course Code": course.get("code", ""),
                "Course Name": course.get("name", ""),
                "Lecturer Name": course.get("lecturer_name") or f"Lecturer #{course.get('lecturer_id', '')}",
                "Enrolled Students": course.get("student_count", 0),
            }
            for course in courses
        ], use_container_width=True, hide_index=True)
    else:
        st.info("No courses have been created yet.")

with create_tab:
    with st.form("create_course_form"):
        code = st.text_input("Course Code", placeholder="CS101")
        name = st.text_input("Course Name", placeholder="Computer Vision")
        lecturer_id = st.number_input("Lecturer ID", min_value=1, value=2, step=1, help="Default lecturer1 ID is 2")
        st.caption("Available lecturers: ID `2` (Dr. Ahmed Mansour / lecturer1) or ID `1` (Admin)")
        submitted = st.form_submit_button("Create Course", type="primary")
    if submitted:
        if not code.strip() or not name.strip():
            ui.show_error("Course code and course name are required.")
        else:
            try:
                api.create_course(code.strip(), name.strip(), int(lecturer_id))
                ui.show_success("Course created successfully!")
                st.rerun()
            except Exception as exc:
                ui.show_error(str(getattr(exc, "message", exc)))

with roster_tab:
    try:
        courses = api.list_courses()
    except Exception as exc:
        courses = []
        ui.show_error(str(getattr(exc, "message", exc)))
    if not courses:
        st.info("Create a course before managing its roster.")
    else:
        selected_course = st.selectbox(
            "Course",
            courses,
            format_func=lambda c: f"{c['code']} · {c['name']}",
            key="roster_course_selector",
        )
        try:
            current_roster = api.get_course_students(selected_course["id"])
            all_students = api.list_students()
        except Exception as exc:
            current_roster, all_students = [], []
            ui.show_error(str(getattr(exc, "message", exc)))
        selected_students = st.multiselect(
            "Select students enrolled in this course",
            options=all_students,
            default=[s for s in all_students if any(r["id"] == s["id"] for r in current_roster)],
            format_func=lambda s: f"{s['student_code']} · {s['full_name']}",
            key=f"roster_students_{selected_course['id']}",
        )
        if st.button("Update Course Roster", type="primary", key=f"update_roster_{selected_course['id']}"):
            try:
                api.update_course_roster(selected_course["id"], [s["id"] for s in selected_students])
                ui.show_success("Course roster updated successfully!")
                st.rerun()
            except Exception as exc:
                ui.show_error(str(getattr(exc, "message", exc)))
