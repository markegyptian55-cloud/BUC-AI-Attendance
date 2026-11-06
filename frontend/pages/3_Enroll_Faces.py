"""Guided, three-pose student face enrollment."""

import streamlit as st
import ui
from api_client import api


ui.inject_custom_css()
user = api.get_current_user()
if not api.is_authenticated() or not user or user.get("role") != "admin":
    st.warning("Administrator access is required. Please sign in with an admin account.")
    st.stop()

ui.page_header(
    "Enroll Faces",
    caption="Capture 3 face poses (Front, Left, Right) with biometric quality checks",
    badge="MANAGE",
)


@st.dialog("Clear biometric profile")
def confirm_clear_faces(student):
    st.write(f"Clear all enrolled face embeddings for **{student['full_name']}** ({student['student_code']})?")
    if st.button("Confirm Clear & Re-enroll", type="primary", key=f"confirm_clear_faces_{student['id']}"):
        try:
            api.clear_student_faces(student["id"])
            for pose in ("front", "left", "right"):
                st.session_state.pop(f"enroll_{student['id']}_{pose}", None)
                st.session_state.pop(f"quality_{student['id']}_{pose}", None)
            ui.show_success("Biometric profile cleared.")
            st.rerun()
        except Exception as exc:
            ui.show_error(str(getattr(exc, "message", exc)))


try:
    students = api.list_students()
except Exception as exc:
    students = []
    ui.show_error(str(getattr(exc, "message", exc)))

if not students:
    st.info("Register a student before enrolling face poses.")
else:
    student = st.selectbox(
        "Select student",
        students,
        format_func=lambda s: f"{s['student_code']} · {s['full_name']} ({s.get('enrolled_faces_count', 0)}/3 enrolled)",
        key="enroll_student_selector",
    )
    student_id = student["id"]
    if int(student.get("enrolled_faces_count", 0)) >= 3:
        st.success("Student has complete 3-pose biometric profile.")
        if st.button("Clear & Re-enroll", key=f"clear_faces_{student_id}"):
            confirm_clear_faces(student)

    poses = [
        ("front", "Front Pose", "|yaw| ≤ 15°, looking straight"),
        ("left", "Left Profile", "yaw ≥ 20°, head turned left"),
        ("right", "Right Profile", "yaw ≤ -20°, head turned right"),
    ]
    columns = st.columns(3)
    for col, (pose, title, guidance) in zip(columns, poses):
        with col:
            st.subheader(title)
            st.caption(guidance)
            camera_tab, upload_tab = st.tabs(["📷 Camera", "📁 Upload"])
            with camera_tab:
                photo = st.camera_input(f"Capture {title.lower()}", key=f"camera_{student_id}_{pose}")
            with upload_tab:
                uploaded = st.file_uploader(f"Upload {title.lower()} photo", type=["jpg", "jpeg", "png"], key=f"upload_{student_id}_{pose}")
            selected_photo = uploaded or photo
            photo_bytes = selected_photo.getvalue() if selected_photo is not None else None
            if selected_photo is not None:
                st.image(photo_bytes, caption=title, use_container_width=True)
                if st.button("Test Photo Quality", key=f"test_quality_{student_id}_{pose}"):
                    try:
                        result = api.check_face_photo(photo_bytes)
                        st.session_state[f"quality_{student_id}_{pose}"] = result
                    except Exception as exc:
                        ui.show_error(str(getattr(exc, "message", exc)))
                quality = st.session_state.get(f"quality_{student_id}_{pose}")
                if quality:
                    if quality.get("is_valid"):
                        width = quality.get("face_width", "—")
                        sharpness = quality.get("blur_score", "—")
                        st.success(f"✅ Valid {quality.get('angle', pose)} pose! Face size: {width}px, Sharpness: {sharpness}")
                    else:
                        st.error(f"❌ {quality.get('message', 'Photo did not pass quality checks.')}")
            if photo_bytes:
                st.session_state[f"enroll_{student_id}_{pose}"] = photo_bytes
            elif selected_photo is None:
                st.session_state.pop(f"enroll_{student_id}_{pose}", None)

    if st.button("Save 3-Pose Biometric Profile", type="primary", use_container_width=True):
        pose_bytes = [st.session_state.get(f"enroll_{student_id}_{pose}") for pose, _, _ in poses]
        if not all(pose_bytes):
            ui.show_error("Capture or upload all three poses before saving the profile.")
        else:
            try:
                api.enroll_student_faces(student_id, *pose_bytes)
                ui.show_success("Successfully enrolled all 3 face poses!")
                st.rerun()
            except Exception as exc:
                ui.show_error(str(getattr(exc, "message", exc)))
