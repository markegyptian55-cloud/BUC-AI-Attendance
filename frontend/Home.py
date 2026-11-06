import streamlit as st

import ui
from api_client import ApiError, api

st.set_page_config(page_title="Attendance AI", page_icon="🎓", layout="wide", initial_sidebar_state="expanded")
ui.inject_custom_css()


def login_page() -> None:
    st.markdown("""<style>
    .login-wrap {max-width:440px;margin:7vh auto 0;padding:30px 34px;background:#FFFDF8;border:1px solid #E4DFD3;border-radius:14px;}
    .login-badge {color:#B5570B;font-size:.7rem;font-weight:700;letter-spacing:.13em;margin:10px 0 4px;}
    .login-caption {color:#5E6878;margin:0 0 20px;}
    </style>""", unsafe_allow_html=True)
    _, center, _ = st.columns([1, 1.15, 1])
    with center:
        with st.container(border=True):
            st.markdown('<div class="login-badge">BADR UNIVERSITY IN CAIRO</div>', unsafe_allow_html=True)
            st.markdown("## 🎓 Attendance AI")
            st.markdown('<div class="login-caption">Sign in to your account</div>', unsafe_allow_html=True)
            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
            if submitted:
                try:
                    api.login(username.strip(), password)
                    st.rerun()
                except ApiError as err:
                    ui.show_error(err.message)
            st.caption("Demo access: admin / admin123  ·  lecturer1 / teach123")


if not api.is_authenticated():
    login_page()
else:
    user = api.get_current_user() or {}
    role = user.get("role")
    p_dashboard = st.Page("pages/1_Dashboard.py", title="Dashboard", icon=":material/dashboard:", default=(role == "lecturer"))
    p_attendance = st.Page("pages/5_Take_Attendance.py", title="Take attendance", icon=":material/fact_check:")
    p_reports = st.Page("pages/6_Reports.py", title="Reports", icon=":material/analytics:")
    p_students = st.Page("pages/2_Students.py", title="Students", icon=":material/group:", default=(role == "admin"))
    p_enroll = st.Page("pages/3_Enroll_Faces.py", title="Enroll faces", icon=":material/face:")
    p_courses = st.Page("pages/4_Courses.py", title="Courses", icon=":material/school:")
    attendance_pages = [p_dashboard, p_attendance, p_reports]
    if role == "lecturer":
        menu = {"ATTENDANCE": attendance_pages}
    elif role == "admin":
        menu = {"MANAGE": [p_students, p_enroll, p_courses], "ATTENDANCE": attendance_pages}
    else:
        api.logout()
        st.rerun()
    with st.sidebar:
        st.markdown("## 🎓 Attendance AI")
        ui.sidebar_profile(user.get("full_name", "User"), role or "")
        if st.button("Sign out", use_container_width=True):
            api.logout()
            st.rerun()
    nav = st.navigation(menu)
    nav.run()
