# Attendance AI — Master Implementation Plan & Step-by-Step Blueprint

**Target System:** Attendance AI (FastAPI + Streamlit + InsightFace + SQLite)  
**Execution Target:** 3–4 Hour Rapid Implementation Sprint  
**Target Architecture:** Local Standalone Deployment on Single Machine  

---

## 1. Project Overview & Architecture

**Attendance AI** is an automated face-recognition university attendance system engineered for Badr University in Cairo (BUC). It replaces manual paper roll-calls with a classroom snapshot recognition pipeline.

### Core Architecture Flow
```
┌─────────────────────────────────────────────────────────────┐
│                       Web Browser                           │
│        Lecturer or Admin (st.camera_input / Upload)         │
└──────────────────────────────┬──────────────────────────────┘
                               │ Localhost (Port 8501)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 Streamlit Frontend App                      │
│   Pages: Login, Dashboard, Students, Enroll, Courses,       │
│          Take Attendance, Reports                           │
│   State: Keeps JWT in st.session_state                      │
│   Calls: Centralized via api_client.py                      │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP JSON + Bearer Token (127.0.0.1:8000)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI Backend App                        │
│   Routers: /auth, /students, /faces, /courses,              │
│            /sessions, /reports                              │
│   ├── Face Engine: InsightFace buffalo_l (SCRFD + ArcFace)  │
│   ├── Quality Gate: Blur, brightness, face dimensions, yaw  │
│   ├── Matcher: In-Memory 512-d Vectors + Cosine Similarity  │
│   └── Attendance Service: Roster aggregation & CSV export   │
└──────────────────────────────┬──────────────────────────────┘
                               │ SQLite Engine (WAL Mode)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                      SQLite Database                        │
│   Tables: users, students, face_embeddings, courses,        │
│           course_students, sessions, attendance_records     │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Directory Layout (Minimal Files)

```
F:\projects\BUC AI Attendance\
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # Lifespan model loader, router mounting, CORS
│   │   ├── config.py            # Pydantic BaseSettings (.env loader)
│   │   ├── db.py                # SQLAlchemy engine with WAL pragma & sessionmaker
│   │   ├── models.py            # 7 SQLAlchemy declarative tables
│   │   ├── schemas.py           # Pydantic request and response schemas
│   │   ├── auth.py              # Argon2 password hash, JWT tokens, require_role
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py          # /api/auth/login, /api/auth/me, /api/health
│   │   │   ├── students.py      # /api/students CRUD, /api/faces/check, /api/students/{id}/faces
│   │   │   ├── courses.py       # /api/courses, /api/courses/{id}/students (roster)
│   │   │   ├── sessions.py      # /api/courses/{id}/sessions, /recognize, /attendance
│   │   │   └── reports.py       # /api/courses/{id}/report (JSON & CSV export)
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── face_engine.py   # InsightFace SCRFD + ArcFace singleton
│   │       ├── quality.py       # Laplacian blur, brightness, 3D landmark yaw check
│   │       └── matcher.py       # In-memory vector matrix, roster filter, greedy 1-to-1
│   ├── scripts/
│   │   ├── create_user.py       # CLI admin & lecturer seeder
│   │   └── evaluate_accuracy.py # Threshold tuning (0.30 to 0.80 sweep)
│   ├── tests/
│   │   ├── test_matcher.py      # Unit tests for vector matching & assignment
│   │   └── test_quality.py      # Unit tests for image quality gates
│   └── requirements.txt
├── frontend/
│   ├── .streamlit/
│   │   └── config.toml          # Custom clean theme (light mode, primary color)
│   ├── Home.py                  # Entrypoint: Login form, session state, st.navigation
│   ├── api_client.py            # Central HTTP wrapper with token management & error handling
│   ├── ui.py                    # Shared components: metric_card, page_header, alert_banner
│   ├── pages/
│   │   ├── 1_Dashboard.py       # Lecturer metrics & active courses
│   │   ├── 2_Students.py        # Student directory & registration form
│   │   ├── 3_Enroll_Faces.py    # Guided 3-pose camera capture (front, left, right)
│   │   ├── 4_Courses.py         # Course management & student roster assignment
│   │   ├── 5_Take_Attendance.py # 3-step wizard (Photos -> Review Table -> Save)
│   │   └── 6_Reports.py         # Attendance percentage table & CSV export
│   └── requirements.txt
├── data/                        # Local SQLite DB & test images (git-ignored)
├── .env.example
├── .gitignore
├── AGENTS.md                    # Ironclad engineering rules & adversarial defenses
└── PROJECT_PLAN.md              # This master step-by-step implementation plan
```

---

## 3. Relational Database Schema (SQLite via SQLAlchemy)

The database consists of 7 tables stored in a single local file (`data/attendance.db`):

```sql
-- 1. System Users (Admin and Lecturers)
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'lecturer'))
);

-- 2. Students Master Registry
CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_code TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    level TEXT NOT NULL,
    group_name TEXT NOT NULL,
    consent_at TIMESTAMP NOT NULL
);

-- 3. Biometric Face Embeddings (512 float32 = 2048 bytes blob)
CREATE TABLE face_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    vector BLOB NOT NULL,
    angle TEXT NOT NULL CHECK(angle IN ('front', 'left', 'right')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Academic Courses
CREATE TABLE courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    lecturer_id INTEGER NOT NULL REFERENCES users(id)
);

-- 5. Course Enrollment Roster
CREATE TABLE course_students (
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    PRIMARY KEY (course_id, student_id)
);

-- 6. Attendance Sessions (Lectures)
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL CHECK(status IN ('open', 'closed'))
);

-- 7. Individual Attendance Records
CREATE TABLE attendance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK(status IN ('present', 'absent', 'excused')),
    source TEXT NOT NULL CHECK(source IN ('auto', 'manual')),
    confidence REAL,
    UNIQUE(session_id, student_id)
);
```

---

## 4. Complete API Endpoint Specifications

All endpoints are hosted under `/api` on `http://127.0.0.1:8000`. Authenticated routes require `Authorization: Bearer <token>`.

| Method | Endpoint | Access Role | Description |
|---|---|---|---|
| `POST` | `/api/auth/login` | Public | Form login returning 8-hour JWT access token |
| `GET` | `/api/auth/me` | Logged in | Returns authenticated user profile |
| `GET` | `/api/health` | Public | System status, model loading state, cached vector count |
| `GET` | `/api/students` | Admin, Lecturer | List students with face enrollment status |
| `POST` | `/api/students` | Admin | Register new student profile (requires consent) |
| `DELETE` | `/api/students/{id}` | Admin | Delete student and cascade delete embeddings |
| `POST` | `/api/faces/check` | Admin | Test photo quality, face count, and head orientation |
| `POST` | `/api/students/{id}/faces`| Admin | Submit 3 photos (front, left, right) for enrollment |
| `DELETE` | `/api/students/{id}/faces`| Admin | Clear face embeddings for student |
| `GET` | `/api/courses` | Admin, Lecturer | List courses (Admin: all, Lecturer: owned) |
| `POST` | `/api/courses` | Admin | Create new course assigned to a lecturer |
| `PUT` | `/api/courses/{id}/students` | Admin | Replace course enrollment roster |
| `POST` | `/api/courses/{id}/sessions` | Lecturer | Open new attendance session for lecture |
| `POST` | `/api/sessions/{id}/recognize` | Lecturer | Submit 1–5 photos; returns recognized, absent, unknown |
| `PUT` | `/api/sessions/{id}/attendance`| Lecturer | Commit reviewed attendance records; close session |
| `GET` | `/api/courses/{id}/report` | Admin, Lecturer | Attendance percentages and downloadable CSV |

---

## 5. Phase-by-Phase Step-by-Step Implementation Checklist

### Phase 1: Environment & Project Scaffolding (~20 mins)
- [x] **Step 1.1:** Create directory layout: `backend/app/routers`, `backend/app/services`, `backend/scripts`, `backend/tests`, `frontend/pages`, `frontend/.streamlit`, `data/`.
- [x] **Step 1.2:** Create `.gitignore` ignoring virtual environments, `data/`, and `.env`.
- [x] **Step 1.3:** Create `.env.example` with default parameters (`SECRET_KEY`, `DATABASE_URL`, `MATCH_THRESHOLD=0.60`, `SIDE_MATCH_THRESHOLD=0.55`, `DET_SIZE=320`).
- [x] **Step 1.4:** Create `backend/requirements.txt` and `frontend/requirements.txt`.
- [x] **Verification:** Verify directory structure exists and requirements files are complete.

---

### Phase 2: Database Schema & Authentication (~35 mins)
- [x] **Step 2.1:** Implement `backend/app/config.py` using `pydantic-settings` to load `.env`.
- [x] **Step 2.2:** Implement `backend/app/db.py`: Configure SQLite with WAL mode (`PRAGMA journal_mode=WAL`), `PRAGMA busy_timeout=30000`, `pool_pre_ping=True`, and sessionmaker.
- [x] **Step 2.3:** Implement `backend/app/models.py`: 7 SQLAlchemy models (`User`, `Student`, `FaceEmbedding`, `Course`, `CourseStudent`, `Session`, `AttendanceRecord`).
- [x] **Step 2.4:** Implement `backend/app/schemas.py`: Pydantic request and response models for all entities.
- [x] **Step 2.5:** Implement `backend/app/auth.py`: Password hashing with Argon2, JWT encoding/decoding with 8h expiration, and `require_role('admin' | 'lecturer')` dependency.
- [x] **Step 2.6:** Implement `backend/scripts/create_user.py`: CLI script to seed initial admin (`admin` / `admin123`) and lecturer (`lecturer1` / `teach123`).
- [x] **Step 2.7:** Implement `backend/app/routers/auth.py`: `/api/auth/login`, `/api/auth/me`, and `/api/health`.
- [x] **Verification:** Run `create_user.py` to seed DB; test `/api/auth/login` via curl or pytest.

---

### Phase 3: Face Perception & Matching Service (~40 mins)
- [x] **Step 3.1:** Implement `backend/app/services/face_engine.py`: Load InsightFace `buffalo_l` singleton at FastAPI lifespan startup with `det_size=(320, 320)`. Wrap CPU inference in synchronous `def` functions.
- [x] **Step 3.2:** Implement `backend/app/services/quality.py`:
  - Face dimensions $\ge 90\text{ px}$.
  - Blur score: Laplacian variance $\ge 50.0$.
  - Brightness score: Mean pixel intensity between $40$ and $215$.
  - 3D landmark yaw angle check: `front` ($|\text{yaw}| \le 12^\circ$), `left` ($\text{yaw} \ge +20^\circ$), `right` ($\text{yaw} \le -20^\circ$).
- [x] **Step 3.3:** Implement `backend/app/services/matcher.py`:
  - Maintain in-memory normalized 512-d embeddings.
  - Filter vectors strictly by course roster.
  - Compute vectorized cosine similarity matrix via `np.dot()`.
  - Apply dual thresholds: $\tau_{\text{front}} = 0.60$, $\tau_{\text{side}} = 0.55$.
  - Greedy 1-to-1 matching (highest score first; eliminate matched pair).
- [x] **Step 3.4:** Implement unit tests in `backend/tests/test_matcher.py` and `backend/tests/test_quality.py`.
- [x] **Verification:** Run `pytest tests/test_matcher.py tests/test_quality.py` to confirm algorithm correctness.

---

### Phase 4: Business REST Routers (~40 mins)
- [x] **Step 4.1:** Implement `backend/app/routers/students.py`:
  - `GET /api/students` (list with face status).
  - `POST /api/students` (add student profile with consent check).
  - `DELETE /api/students/{id}` (cascade delete).
- [x] **Step 4.2:** Implement `backend/app/routers/faces.py`:
  - `POST /api/faces/check` (instant preview check for blur, size, brightness, yaw).
  - `POST /api/students/{id}/faces` (atomic 3-shot enrollment: front, left, right).
  - `DELETE /api/students/{id}/faces` (revoke stored embeddings).
- [x] **Step 4.3:** Implement `backend/app/routers/courses.py`:
  - `GET /api/courses` (Admin: all, Lecturer: owned).
  - `POST /api/courses` (create course).
  - `PUT /api/courses/{id}/students` (replace roster).
- [x] **Step 4.4:** Implement `backend/app/routers/sessions.py`:
  - `POST /api/courses/{id}/sessions` (open attendance session).
  - `POST /api/sessions/{id}/recognize` (accept 1–5 photos, return recognized, absent, and unknown count).
  - `PUT /api/sessions/{id}/attendance` (commit reviewed attendance records).
- [x] **Step 4.5:** Implement `backend/app/routers/reports.py`:
  - `GET /api/courses/{id}/report` (attendance percentage per student and streaming CSV export).
- [x] **Step 4.6:** Wire routers into `backend/app/main.py` with lifespan model loader and CORS.
- [x] **Verification:** Start Uvicorn and verify all 16 endpoints appear in `http://127.0.0.1:8000/docs`.

---

### Phase 5: Streamlit Frontend Client (~50 mins)
- [x] **Step 5.1:** Implement `frontend/.streamlit/config.toml`: Official brand theme settings (warm linen `#F7F5EF`, primary terracotta `#B5570B`, deep navy `#14213D`).
- [x] **Step 5.2:** Implement `frontend/api_client.py`: Centralized HTTP caller wrapping all 16 endpoints with token management and error formatting.
- [x] **Step 5.3:** Implement `frontend/ui.py`: Shared UI components and CSS injection engine matching Slides 08 & 09 (`page_header`, `step_wizard`, `metric_cards`, `confidence_bar_html`, `sidebar_profile`, `show_error`, `show_success`).
- [x] **Step 5.4:** Implement `frontend/Home.py`: Login card, JWT storage in `st.session_state`, and role-based dynamic navigation via `st.navigation`.
- [x] **Step 5.5 (Star Feature):** Implement `frontend/pages/5_Take_Attendance.py`: 3-step wizard (Step 1: Photos $\rightarrow$ Step 2: Review Table matching Slide 09 mockup $\rightarrow$ Step 3: Save & Summary).
- [x] **Step 5.6:** Implement Admin pages:
  - `frontend/pages/2_Students.py`: Searchable student table + Add Student form with consent checkbox.
  - `frontend/pages/3_Enroll_Faces.py`: Student picker, 3-pose progress bar (front, left, right), webcam / upload tabs, instant quality indicators, atomic save.
  - `frontend/pages/4_Courses.py`: Course management + multi-select roster picker.
- [x] **Step 5.7:** Implement Lecturer companion pages:
  - `frontend/pages/1_Dashboard.py`: Metric cards (courses, active sessions, attendance rates).
  - `frontend/pages/6_Reports.py`: Attendance percentage table with progress bars + one-click CSV download.
- [x] **Verification:** Launch `streamlit run Home.py` and test navigation between roles.

---

### Phase 6: End-to-End Verification & Walkthrough (~20 mins)
- [x] **Step 6.1:** Start backend (`uvicorn app.main:app --port 8000`) and frontend (`streamlit run Home.py --port 8501`).
- [x] **Step 6.2:** Admin verification: Login as `admin`, create student, enroll 3 face poses via webcam, create course, assign roster.
- [x] **Step 6.3:** Lecturer verification: Login as `lecturer1`, start session, upload/capture photo, verify recognition review checklist, commit attendance, and download CSV report.
- [x] **Step 6.4:** Edge case verification: Verify unknown stranger stays unrecognized, blurry photo is rejected, and closed session rejects duplicate submissions.
