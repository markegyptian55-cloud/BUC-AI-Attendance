# Project Execution Evidence Gallery

This directory contains real-world screenshots, automated test proofs, and an operational tutorial video proving the live operation of the Attendance AI system.

---

### Official Walkthrough Video

#### Quick Operational Tutorial (الفيديو الإرشادي السريع)
- **File:** [`attendance_ai_tutorial.mp4`](./attendance_ai_tutorial.mp4)
- **Duration:** **119.2 seconds** (~2.0 minutes)
- **Format:** 1080p Full HD (`1920x1080`), 24 FPS, H.264 / AAC (File size: ~4.23 MB).
- **Narration:** Fast 10-step operational guide from login to CSV export.

---

### Verification Screenshots Gallery

| # | Filename | Feature / Screen | Verification Details |
|---|---|---|---|
| **01** | [`01_enroll_faces_3poses_success.jpg`](./01_enroll_faces_3poses_success.jpg) | Enroll Faces (3-Pose Biometric Capture) | Real camera capture of Front, Left, and Right poses with instant quality checks passing: `Valid front pose!`, `Valid left pose!`, and `Valid right pose!`. |
| **02** | [`02_create_course_screen.png`](./02_create_course_screen.png) | Courses & Rosters (Create Course Form) | Creating new course `cs101` (Computer Vision). |
| **03** | [`03_create_course_success.png`](./03_create_course_success.png) | Courses & Rosters (Create Form with Lecturer 2) | Setting Lecturer ID to `2` (`Dr. Ahmed Mansour`). |
| **04** | [`04_course_catalog_created.png`](./04_course_catalog_created.png) | Courses Catalog | Catalog table showing `CS101 · Computer vision` assigned to `Dr. Ahmed Mansour`. |
| **05** | [`05_login_admin.png`](./05_login_admin.png) | Login Portal | Academic university sign-in portal. |
| **06** | [`06_take_attendance_camera_step.jpg`](./06_take_attendance_camera_step.jpg) | Take Attendance (Camera Step) | Classroom camera snapshot feed for session attendance. |
| **07** | [`07_take_attendance_empty_roster_review.png`](./07_take_attendance_empty_roster_review.png) | Take Attendance (Review with Empty Roster) | Review table showing `Unknown faces: 1 in photos` and `0 of roster` because course roster is empty. |
| **08** | [`08_take_attendance_done_zero.png`](./08_take_attendance_done_zero.png) | Attendance Saved (Zero Roster) | Summary showing `Students in roster: 0`, `Present: 0`, `Absent: 0`. |
| **09** | [`09_manage_roster_add_student.png`](./09_manage_roster_add_student.png) | Manage Roster (Add Student to Course) | Selecting course `CS101` and adding enrolled student `Mohamed Mostafa MOHAMED ElbaSuny` then clicking `Update Course Roster`. |
| **10** | [`10_course_catalog_1_student.png`](./10_course_catalog_1_student.png) | Course Catalog (Enrolled Students: 1) | Verification that `CS101` now reflects `Enrolled Students: 1`. |
| **11** | [`11_take_attendance_success_91pct.png`](./11_take_attendance_success_91pct.png) | Take Attendance (Biometric Match: 91%) | Flawless recognition: `Recognized: 1 of roster`, `Not found: 0 students`, `Unknown faces: 0 in photos`, student marked `Present` with **91% Confidence** bar. |
| **12** | [`12_dashboard_overview.png`](./12_dashboard_overview.png) | Lecturer & Admin Dashboard | Active courses overview, 1 enrolled student, quick action shortcuts. |
| **13** | [`13_attendance_reports.png`](./13_attendance_reports.png) | Official Attendance Reports | Cumulative attendance table (50.0%), student at-risk indicator, and `Download Official Attendance Report (CSV)`. |
