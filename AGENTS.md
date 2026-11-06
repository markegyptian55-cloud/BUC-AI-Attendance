# AGENTS.md — Ironclad Engineering Rules & System Execution Plan
**System:** Attendance AI (FastAPI + Streamlit + InsightFace + SQLite)  
**Target:** 3–4 Hour Rapid Implementation Sprint  
**Architecture:** Local Standalone Deployment on Single Machine  

---

## 1. System Vision & Architecture Principles

1. **Local-First & Zero Overhead:** Everything runs locally on one laptop. No cloud subscriptions, no external database servers, no Docker complexity.
2. **Pretrained Metric Learning (Zero Retraining):** We use InsightFace `buffalo_l` (`SCRFD` face detector + `ArcFace ResNet-50` embedder). Student registration simply extracts a 512-d unit vector and saves it to SQLite. **Never fine-tune or retrain.**
3. **Course-Roster Scoped Matching:** Classroom faces are matched **strictly** against the active course roster, never against the entire university database. This drastically reduces false positives and ensures sub-second matrix matching.
4. **Human-in-the-Loop Review Gate:** The AI proposes attendance; the lecturer audits the checklist and commits the final record. No automated destructive actions.
5. **Classroom Privacy:** Classroom photos are analyzed in volatile RAM and discarded immediately. No video feeds or classroom pictures are persisted to disk.

---

## 2. The Adversarial "Pitfall Defense" Matrix (Real-World Failures & Solutions)

Based on empirical research into failed and buggy open-source face attendance projects, every agent and engineer working on this repository **MUST strictly enforce** these defenses:

| Domain | How Other Projects Fail (Common Bugs) | Strict Rule & Solution in Our Codebase |
|---|---|---|
| **FastAPI Concurrency** | Declaring `async def` on face recognition routes. Heavy CPU operations in `async def` freeze Python's single asyncio event loop, hanging all other incoming requests. | **Rule 1:** Always declare CPU-bound endpoints (CV detection, embedding, matching) as standard `def`, NOT `async def`. FastAPI automatically runs `def` routes in an external thread pool (`anyio.to_thread`), preventing event loop blockage. |
| **Model Lifecycle** | Initializing `FaceAnalysis()` inside request handlers or re-loading models on each request, causing 10s latency and massive memory leaks. | **Rule 2:** Load `FaceAnalysis(name='buffalo_l')` **once** inside FastAPI's `lifespan` startup hook and attach to `app.state.face_engine`. Configure `det_size=(320, 320)` for optimal CPU speed. |
| **SQLite Concurrency** | Multi-threaded requests throw `sqlite3.OperationalError: database is locked` during concurrent writes. | **Rule 3:** Always initialize SQLite engine with WAL mode (`PRAGMA journal_mode=WAL`), a generous timeout (`PRAGMA busy_timeout=30000`), `pool_pre_ping=True`, and `timeout=30`. Keep write transactions short-lived. |
| **Streamlit State Trap** | Placing `st.button` inside another `if st.button()` block. On the second click, Streamlit reruns from line 1, resetting the parent button to `False` and destroying the inner action. | **Rule 4:** Never nest `st.button` directly. Use a **State Machine pattern** driven by `st.session_state.stage` or persistent boolean flags combined with `st.rerun()`. |
| **Streamlit Buffer Bug** | Calling `file.read()` multiple times on `st.camera_input` or file uploaders, resulting in an empty buffer (`b''`) on subsequent operations. | **Rule 5:** Always extract bytes once via `file.getvalue()` and decode into OpenCV using `cv2.imdecode(np.frombuffer(bytes, np.uint8), cv2.IMREAD_COLOR)`. |
| **Matching Logic** | Using unnormalized Euclidean distance or greedy matching without replacement, allowing one face to be assigned to multiple students or vice versa. | **Rule 6:** Enforce L2-normalized vectors ($\|\mathbf{v}\| = 1$). Compute cosine similarity matrix via a single vectorized NumPy dot product: `sims = np.dot(query_mat, roster_mat.T)`. Apply greedy 1-to-1 matching (highest score first; eliminate matched pair). |
| **Threshold Bleed** | Using a single global threshold, causing side-profile faces to be missed or strangers to be marked present. | **Rule 7:** Apply dual thresholds: $\tau_{\text{front}} = 0.60$ and $\tau_{\text{side}} = 0.55$. Strangers with scores below threshold MUST be classified as `unknown`. |
| **API Error Handling** | Returning unhandled 500 exceptions with raw Python tracebacks when 0 faces are detected in an image. | **Rule 8:** Never return a 500 for expected CV edge-cases. Catch detection errors and return structured `400 Bad Request` with user-friendly error codes (`NO_FACE_DETECTED`, `MULTIPLE_FACES_DETECTED`, `POOR_QUALITY`). |
| **Architecture Bloat** | Creating dozens of tiny files and unnecessary abstractions for a 3-hour project. | **Rule 9 (Code Simplification):** Keep the codebase minimal. 1 shared database module, 1 auth module, 1 face service, 1 matcher, and 1 consolidated API client. Maximum readability, minimal file count. |

---

## 3. System Directory Layout (Minimal Files)

```
F:\projects\BUC AI Attendance\
├── backend/
│   ├── app/
│   │   ├── main.py              # Lifespan loader, router mounting, CORS
│   │   ├── config.py            # Pydantic Settings (.env)
│   │   ├── db.py                # Engine with WAL pragma, sessionmaker, Base
│   │   ├── models.py            # 7 SQLAlchemy tables (users, students, embeddings, courses, rosters, sessions, records)
│   │   ├── schemas.py           # Pydantic request/response schemas
│   │   ├── auth.py              # Argon2 hashing, JWT encode/decode, require_role
│   │   ├── routers/
│   │   │   ├── auth.py          # /api/auth/login, /api/auth/me, /api/health
│   │   │   ├── students.py      # /api/students CRUD, /api/faces/check, /api/students/{id}/faces
│   │   │   ├── courses.py       # /api/courses, /api/courses/{id}/students
│   │   │   ├── sessions.py      # /api/courses/{id}/sessions, /recognize, /attendance
│   │   │   └── reports.py       # /api/courses/{id}/report (JSON & CSV)
│   │   └── services/
│   │       ├── face_engine.py   # InsightFace SCRFD + ArcFace singleton
│   │       ├── quality.py       # Blur, size, brightness, 3D landmark yaw check
│   │       └── matcher.py       # In-memory vector cache, matrix dot product, greedy matching
│   ├── scripts/
│   │   └── create_user.py       # CLI admin & lecturer seeder
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
└── AGENTS.md                    # This master rules and execution contract
```

---

## 4. Phase-by-Phase Implementation Blueprint

### Phase 1: Foundations & Scaffolding (~20 mins)
- Scaffold `backend/` and `frontend/` directory trees.
- Create `.gitignore` and `.env.example`.
- Create `backend/requirements.txt` and `frontend/requirements.txt`.
- Set up SQLite engine with WAL mode and connection pooling in `backend/app/db.py`.

### Phase 2: Core Persistence & Security (~35 mins)
- Implement all 7 SQLAlchemy models in `backend/app/models.py`.
- Implement password hashing (Argon2) and JWT token validation in `backend/app/auth.py`.
- Build CLI user creation script `backend/scripts/create_user.py`.
- Build `/api/auth/login`, `/api/auth/me`, and `/api/health` in `backend/app/routers/auth.py`.

### Phase 3: Face Perception & Matching Service (~40 mins)
- Build `backend/app/services/face_engine.py` with InsightFace singleton loaded in lifespan.
- Build `backend/app/services/quality.py` (face size $\ge 90\text{px}$, Laplacian variance $\ge 50$, brightness $40-215$, 3D landmark yaw angles).
- Build `backend/app/services/matcher.py` (matrix cosine similarity, roster filtering, greedy 1-to-1 assignment).
- Add unit tests in `backend/tests/test_matcher.py` to prove math before touching the UI.

### Phase 4: Business REST Routers (~40 mins)
- Build `backend/app/routers/students.py` (student CRUD, face check, atomic 3-pose enrollment).
- Build `backend/app/routers/courses.py` (course CRUD, roster assignment).
- Build `backend/app/routers/sessions.py` (open session, `/recognize` endpoint for 1–5 photos, `/attendance` commit).
- Build `backend/app/routers/reports.py` (attendance percentages and streaming CSV export).

### Phase 5: Streamlit Frontend Client (~50 mins)
- Build `frontend/api_client.py` wrapping all backend endpoints with token injection and error handling.
- Build `frontend/Home.py` with login form, session state management, and role-based `st.navigation`.
- Build Admin screens: `2_Students.py`, `3_Enroll_Faces.py` (3-pose capture with live quality feedback), `4_Courses.py`.
- Build Lecturer screens: `1_Dashboard.py`, `5_Take_Attendance.py` (Photo upload/webcam $\rightarrow$ Review table $\rightarrow$ Save), `6_Reports.py`.

### Phase 6: End-to-End Verification & Walkthrough (~20 mins)
- Start FastAPI backend (`uvicorn app.main:app --port 8000`).
- Start Streamlit frontend (`streamlit run Home.py --port 8501`).
- Execute complete user journey:
  1. Login as Admin.
  2. Add Student + Enroll 3 face poses.
  3. Create Course + Assign Student to roster.
  4. Login as Lecturer + Open Session.
  5. Upload/Snap photo + Run Recognition.
  6. Verify detection, audit checklist, and commit attendance.
  7. Export verified CSV report.

---

## 5. Director-Executor Operating Protocol (Antigravity Director + Codex CLI Executor)

This protocol governs all development interactions throughout the project:

1. **Role Division:**
   - **Antigravity (The Director / Lead Architect):** Formulates expert, highly-contextualized task prompts for Codex CLI, audits the generated outputs with hostile code reviews, identifies errors, issues targeted correction prompts, and delivers structured status reports to the User.
   - **Codex CLI (The Executor):** Executes terminal commands, file creation, code implementation, and automated tests under direct prompt supervision.
   - **User (The Executive Sponsor):** Reviews the Director's report at the end of each step and issues explicit approval before the Director is permitted to instruct Codex CLI on the subsequent step.

2. **Step-by-Step Execution Cycle:**
   ```
   [Antigravity] Generates Expert Task Prompt
         │
         ▼
   [Codex CLI] Executes Implementation
         │
         ▼
   [Antigravity] Hostile Audit & Adversarial Review
         │
      ┌──┴────────────────────────┐
      ▼ (Bugs Found)              ▼ (Zero Flaws)
   Critique & Fix Prompt     Executive Report & Assessment
      │                           │
      └──► [Codex CLI Fixes]      ▼
                             [User Approval Gate] ──► Advance to Next Step
   ```

3. **Strict Gatekeeping Rule:**
   Under **NO** circumstances may Antigravity advance to the next step in `PROJECT_PLAN.md` without explicit user authorization.

4. **Codex CLI Model & Resource Budgeting:**
   - **Primary Model:** `gpt-6-luna` (as configured in `~/.codex/config.toml`) or `gpt-5.5` with dynamic reasoning effort:
     - `low` for boilerplate, scaffolding, and file layouts (Phase 1).
     - `medium` for data models, routers, and Streamlit state management (Phases 2, 4, 5).
     - `high` for vector math, ArcFace matrix operations, and concurrency locks (Phase 3).
   - **Reporting Requirement:** After every completed step, Antigravity reports:
     - Task accuracy and precision score (out of 100%).
     - Verification findings and functional purpose of the step.
     - Active Codex model, reasoning effort level, and context budget status.

