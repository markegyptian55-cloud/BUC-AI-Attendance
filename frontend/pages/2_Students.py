"""Admin student directory and consent-aware registration."""

import streamlit as st
import ui
from api_client import api


ui.inject_custom_css()
user = api.get_current_user()
if not api.is_authenticated() or not user or user.get("role") != "admin":
    st.warning("Administrator access is required. Please sign in with an admin account.")
    st.stop()

ui.page_header(
    "Students",
    caption="Student directory, biometric consent status, and registration",
    badge="MANAGE",
)


@st.dialog("Confirm Deletion")
def confirm_student_delete(student):
    st.write(f"Delete **{student['full_name']}** ({student['student_code']})?")
    st.write("Are you sure? This will permanently delete the student and their enrolled biometric embeddings.")
    if st.button("Confirm Deletion", type="primary", key=f"confirm_delete_{student['id']}"):
        try:
            api.delete_student(student["id"])
            ui.show_success("Student deleted successfully.")
            st.rerun()
        except Exception as exc:
            ui.show_error(str(getattr(exc, "message", exc)))


directory_tab, register_tab = st.tabs(["📋 Student Directory", "➕ Register Student"])
with directory_tab:
    search = st.text_input("Search by name or student code", key="student_search")
    try:
        students = api.list_students(search=search if search else None)
    except Exception as exc:
        students = []
        ui.show_error(str(getattr(exc, "message", exc)))

    complete = sum(int(s.get("enrolled_faces_count", 0)) >= 3 for s in students)
    ui.metric_cards([
        ("Total students", str(len(students))),
        ("Students with enrolled faces", str(complete)),
        ("Students pending faces", str(len(students) - complete)),
    ])
    if students:
        for student in students:
            count = int(student.get("enrolled_faces_count", 0))
            face_status = "✅ 3 Poses" if count >= 3 else f"⚠️ {count}/3"
            cols = st.columns([1.2, 2, 1, 1, 1.2, 0.7])
            values = [student.get("student_code", ""), student.get("full_name", ""), student.get("level", ""), student.get("group_name", ""), face_status]
            for col, value in zip(cols, values):
                with col:
                    st.write(value)
            with cols[-1]:
                if st.button("🗑️", key=f"delete_student_{student['id']}", help="Delete student"):
                    confirm_student_delete(student)
    else:
        st.info("No students found.")

with register_tab:
    with st.form("register_student_form"):
        student_code = st.text_input("Student Code", placeholder="20210042")
        full_name = st.text_input("Full Name")
        level = st.selectbox("Level", ["Level 1", "Level 2", "Level 3", "Level 4"])
        group_name = st.selectbox("Group Name", ["Group A", "Group B", "Group C", "Group D"])
        consent = st.checkbox("Student signed the biometric face-recognition consent agreement", value=False)
        submitted = st.form_submit_button("Register Student", type="primary")
    if submitted:
        if not student_code.strip() or not full_name.strip():
            ui.show_error("Student code and full name are required.")
        elif not consent:
            ui.show_error("Biometric consent is legally required before registering a student.")
        else:
            try:
                api.create_student(student_code.strip(), full_name.strip(), level, group_name, consent=True)
                ui.show_success("Student registered successfully!")
                st.rerun()
            except Exception as exc:
                ui.show_error(str(getattr(exc, "message", exc)))
