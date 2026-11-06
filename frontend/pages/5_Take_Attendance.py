"""Three-step attendance workflow: capture, review, and save."""

import streamlit as st
import ui
from api_client import ApiError, api


def _seed_state() -> None:
    defaults = {
        "att_step": 1,
        "att_course_id": None,
        "att_session_id": None,
        "att_recognition": None,
        "att_checklist": {},
        "att_saved_records": [],
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _show_error(exc: Exception) -> None:
    ui.show_error(getattr(exc, "message", str(exc)))


def _course_label(course: dict) -> str:
    return f"{course.get('code', '')} · {course.get('name', '')}"


def _run_recognition(course: dict, photos: list[tuple[str, bytes, str]]) -> None:
    try:
        with st.spinner("SCRFD detecting faces & ArcFace matching with course roster..."):
            result = api.recognize_faces(st.session_state["att_session_id"], photos)
            roster = api.get_course_students(course["id"])
        recognized = {int(item["student_id"]): item for item in result.get("recognized_students", [])}
        absent = {int(item["id"]): item for item in result.get("absent_students", [])}
        checklist = {}
        # The recognition response is roster-scoped; include each roster row once.
        for student in roster:
            student_id = int(student["id"])
            match = recognized.get(student_id)
            checklist[student_id] = {
                "student_id": student_id,
                "student_code": student.get("student_code", ""),
                "full_name": student.get("full_name", ""),
                "status": "present" if match else "absent",
                "confidence": match.get("confidence") if match else None,
                "source": "auto" if match else "manual",
            }
        # Keep any recognized record even if an older API response omits it from roster.
        for student_id, match in recognized.items():
            checklist.setdefault(student_id, {
                "student_id": student_id,
                "student_code": match.get("student_code", ""),
                "full_name": match.get("full_name", ""),
                "status": "present",
                "confidence": match.get("confidence"),
                "source": "auto",
            })
        for student_id, student in absent.items():
            checklist.setdefault(student_id, {
                "student_id": student_id,
                "student_code": student.get("student_code", ""),
                "full_name": student.get("full_name", ""),
                "status": "absent",
                "confidence": None,
                "source": "manual",
            })
        st.session_state["att_recognition"] = result
        st.session_state["att_checklist"] = checklist
        st.session_state["att_step"] = 2
        st.rerun()
    except ApiError as exc:
        _show_error(exc)


def _photos_step(courses: list[dict]) -> None:
    ui.page_header("Take Attendance", caption="Select course and provide classroom photos", badge="ATTENDANCE")
    ui.step_wizard(current_step=1)
    course_ids = [course["id"] for course in courses]
    selected_id = st.session_state.get("att_course_id")
    selected_index = course_ids.index(selected_id) if selected_id in course_ids else 0
    selected = st.selectbox("Course", courses, index=selected_index, format_func=_course_label)
    st.session_state["att_course_id"] = selected["id"]

    try:
        sessions = api.list_sessions(selected["id"])
        open_session = next((item for item in sessions if item.get("status") == "open"), None)
        if open_session:
            st.session_state["att_session_id"] = open_session["id"]
            st.success("An open lecture session is ready.")
        else:
            st.session_state["att_session_id"] = None
            if st.button("Open New Lecture Session", key="att_open_session"):
                try:
                    opened = api.open_session(selected["id"])
                    st.session_state["att_session_id"] = opened["id"]
                    st.rerun()
                except ApiError as exc:
                    _show_error(exc)
    except ApiError as exc:
        _show_error(exc)

    upload_tab, camera_tab = st.tabs(["📁 Upload Photos (1–5)", "📷 Camera Snapshot"])
    photos: list[tuple[str, bytes, str]] = []
    with upload_tab:
        uploaded = st.file_uploader("Choose classroom photos", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key="att_uploads")
        if uploaded:
            for file in uploaded[:5]:
                content = file.getvalue()  # Read each Streamlit upload buffer exactly once.
                photos.append((file.name, content, "image/jpeg"))
                st.image(content, caption=file.name, width=180)
            if len(uploaded) > 5:
                st.warning("Choose no more than five photos.")
    with camera_tab:
        snapshot = st.camera_input("Take one classroom snapshot", key="att_camera")
        if snapshot is not None:
            content = snapshot.getvalue()
            photos.append((getattr(snapshot, "name", "classroom.jpg"), content, "image/jpeg"))
            st.image(content, caption="Camera snapshot", width=240)

    if st.button("Run Face Recognition →", type="primary", key="att_recognize"):
        if not st.session_state.get("att_session_id"):
            try:
                opened = api.open_session(selected["id"])
                st.session_state["att_session_id"] = opened["id"]
            except ApiError as exc:
                _show_error(exc)
                st.stop()
        if not 1 <= len(photos) <= 5:
            ui.show_error("Please capture a photo first (click 'Take Photo' under the camera) or upload photos.")
        else:
            _run_recognition(selected, photos)


def _review_step(courses: list[dict]) -> None:
    course = next((item for item in courses if item.get("id") == st.session_state.get("att_course_id")), {})
    name = _course_label(course) if course else "Course"
    cols = st.columns([4, 3])
    with cols[0]:
        st.markdown(f'<div style="color:{ui.COLOR_TEXT_MUTED};font-size:1.05rem;font-weight:600;padding-top:10px">{name} · session: check the list, then save</div>', unsafe_allow_html=True)
    with cols[1]:
        ui.step_wizard(current_step=2)

    checklist = st.session_state["att_checklist"]
    recognized_count = sum(item["confidence"] is not None for item in checklist.values())
    absent_count = len(checklist) - recognized_count
    recognition = st.session_state.get("att_recognition") or {}
    ui.metric_cards([
        ("Recognized", f"{recognized_count} of roster"),
        ("Not found", f"{absent_count} students"),
        ("Unknown faces", f"{recognition.get('unknown_faces_count', 0)} in photos"),
    ])
    if st.button("← Retake photos", key="att_retake"):
        st.session_state["att_step"] = 1
        st.rerun()

    headers = st.columns([1.2, 4, 2, 4])
    for column, title in zip(headers, ("Present", "Student", "Code", "Confidence")):
        with column:
            st.markdown(
                f'<div class="review-table-header" style="background:{ui.COLOR_SIDEBAR_BG};padding:10px 8px;border-radius:6px">{title}</div>',
                unsafe_allow_html=True,
            )
    ordered = sorted(checklist.values(), key=lambda item: (item["status"] != "present", item["student_code"], item["full_name"]))
    for student in ordered:
        c_chk, c_name, c_code, c_conf = st.columns([1.2, 4, 2, 4])
        with c_chk:
            checked = st.checkbox("", value=student["status"] == "present", key=f"att_check_{student['student_id']}", label_visibility="collapsed")
        student["status"] = "present" if checked else "absent"
        with c_name:
            st.markdown(f'<span style="color:{ui.COLOR_TEXT_PRIMARY};font-weight:600">{student["full_name"]}</span>', unsafe_allow_html=True)
        with c_code:
            st.markdown(f'<span style="color:{ui.COLOR_TEXT_MUTED}">{student["student_code"]}</span>', unsafe_allow_html=True)
        with c_conf:
            if student["confidence"] is not None:
                st.markdown(ui.confidence_bar_html(float(student["confidence"]) * 100), unsafe_allow_html=True)
            else:
                st.markdown(f'<span style="color:{ui.COLOR_TEXT_MUTED};font-style:italic">not found: tick if present</span>', unsafe_allow_html=True)
        st.markdown(f'<div style="border-bottom:1px solid {ui.COLOR_BORDER};margin:0 0 8px"></div>', unsafe_allow_html=True)

    left, spacer, right = st.columns([1.5, 4, 1.5])
    with left:
        if st.button("Mark all present", key="att_all_present"):
            for item in checklist.values():
                item["status"] = "present"
            st.rerun()
    with spacer:
        if st.button("Mark all absent", key="att_all_absent"):
            for item in checklist.values():
                item["status"] = "absent"
            st.rerun()
    with right:
        if st.button("Save attendance", type="primary", key="att_save"):
            records = [{
                "student_id": item["student_id"],
                "status": item["status"],
                "source": "auto" if item.get("confidence") is not None and item["status"] == "present" else "manual",
                "confidence": item.get("confidence"),
            } for item in checklist.values()]
            try:
                saved = api.commit_attendance(st.session_state["att_session_id"], records)
                st.session_state["att_saved_records"] = saved
                st.session_state["att_step"] = 3
                ui.show_success("Attendance successfully committed and session closed!")
                st.rerun()
            except ApiError as exc:
                _show_error(exc)


def _done_step(courses: list[dict]) -> None:
    ui.page_header("Attendance Saved", caption="Session successfully closed and records committed", badge="COMPLETE")
    ui.step_wizard(current_step=3)
    course = next((item for item in courses if item.get("id") == st.session_state.get("att_course_id")), {})
    records = st.session_state.get("att_saved_records", [])
    present = sum(item.get("status") == "present" for item in records)
    absent = sum(item.get("status") == "absent" for item in records)
    ui.metric_cards([("Students in roster", str(len(records))), ("Present", str(present)), ("Absent", str(absent))])
    try:
        csv_bytes = api.get_course_report_csv(st.session_state["att_course_id"])
        st.download_button("📥 Download Course Attendance Report (CSV)", data=csv_bytes,
                           file_name=f"attendance_{course.get('code', 'course')}.csv", mime="text/csv")
    except ApiError as exc:
        _show_error(exc)
    if st.button("Take Attendance for Another Lecture", key="att_another"):
        st.session_state["att_step"] = 1
        st.session_state["att_session_id"] = None
        st.session_state["att_recognition"] = None
        st.session_state["att_checklist"] = {}
        st.session_state["att_saved_records"] = []
        st.rerun()


ui.inject_custom_css()
if not api.is_authenticated():
    st.warning("Please sign in from the Home page.")
    st.stop()
user = api.get_current_user() or {}
_seed_state()

try:
    courses = api.list_courses()
except ApiError as exc:
    _show_error(exc)
    courses = []

if not courses:
    st.warning("No courses are available. Ask an administrator to assign a course and roster.")
    st.stop()

if st.session_state["att_step"] == 1:
    _photos_step(courses)
elif st.session_state["att_step"] == 2:
    _review_step(courses)
else:
    _done_step(courses)
