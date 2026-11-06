"""API tests for attendance session recognition and commits."""

from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

try:
    from backend.app import models
    from backend.app.auth import get_current_user
    from backend.app.db import get_db
    from backend.app.routers import sessions as sessions_router
    from backend.app.routers.sessions import router
except ModuleNotFoundError:
    from app import models
    from app.auth import get_current_user
    from app.db import get_db
    from app.routers import sessions as sessions_router
    from app.routers.sessions import router


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False)
    with testing_session() as db:
        admin = models.User(username="admin", hashed_password="unused", full_name="Admin", role="admin")
        lecturer = models.User(username="lecturer", hashed_password="unused", full_name="Lecturer", role="lecturer")
        other = models.User(username="other", hashed_password="unused", full_name="Other", role="lecturer")
        db.add_all([admin, lecturer, other])
        db.flush()
        course = models.Course(code="CS101", name="Computing", lecturer_id=lecturer.id)
        db.add(course)
        db.flush()
        students = [
            models.Student(student_code=f"S{i:03}", full_name=f"Student {i}", level="2", group_name="A", consent_at=datetime.now(timezone.utc))
            for i in (1, 2)
        ]
        db.add_all(students)
        db.flush()
        db.add_all(models.CourseStudent(course_id=course.id, student_id=s.id) for s in students)
        db.commit()
        ids = {"admin": admin.id, "lecturer": lecturer.id, "other": other.id, "course": course.id, "students": [s.id for s in students]}

    app = FastAPI()
    app.include_router(router)

    def override_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.state.user_id = ids["lecturer"]

    def current_user():
        with testing_session() as db:
            return db.query(models.User).filter_by(id=app.state.user_id).one()

    app.dependency_overrides[get_current_user] = current_user
    with TestClient(app) as api:
        yield api, app, testing_session, ids
    models.Base.metadata.drop_all(engine)
    engine.dispose()


def test_open_session_success(client):
    api, _, _, ids = client
    response = api.post(f"/api/courses/{ids['course']}/sessions")
    assert response.status_code == 200
    assert response.json()["status"] == "open"


def test_open_session_forbidden(client):
    api, app, _, ids = client
    app.state.user_id = ids["other"]
    assert api.post(f"/api/courses/{ids['course']}/sessions").status_code == 403


def test_get_sessions_list(client):
    api, _, _, ids = client
    opened = api.post(f"/api/courses/{ids['course']}/sessions").json()
    response = api.get(f"/api/courses/{ids['course']}/sessions")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [opened["id"]]


def test_session_detail_and_course_access(client):
    api, app, _, ids = client
    opened = api.post(f"/api/courses/{ids['course']}/sessions").json()
    assert api.get(f"/api/sessions/{opened['id']}").status_code == 200
    app.state.user_id = ids["other"]
    assert api.get(f"/api/sessions/{opened['id']}").status_code == 403
    assert api.get("/api/sessions/999").status_code == 404


def test_recognize_closed_session(client):
    api, _, testing_session, ids = client
    opened = api.post(f"/api/courses/{ids['course']}/sessions").json()
    with testing_session() as db:
        db.query(models.Session).filter_by(id=opened["id"]).update({"status": "closed"})
        db.commit()
    response = api.post(f"/api/sessions/{opened['id']}/recognize", files={"photos": ("x.jpg", b"image", "image/jpeg")})
    assert response.status_code == 400
    assert response.json()["detail"] == "Session is closed"


@pytest.mark.parametrize("files", [[], [("x.jpg", b"x", "image/jpeg")] * 6])
def test_recognize_photo_validation(client, files):
    api, _, _, ids = client
    opened = api.post(f"/api/courses/{ids['course']}/sessions").json()
    response = api.post(f"/api/sessions/{opened['id']}/recognize", files=[("photos", item) for item in files])
    assert response.status_code == 400


def test_recognize_mocked_matching(client):
    api, _, _, ids = client
    opened = api.post(f"/api/courses/{ids['course']}/sessions").json()
    match = {
        "recognized": [{"student_id": ids["students"][0], "student_code": "S001", "full_name": "Student 1", "confidence": 0.91}],
        "matched_student_ids": [ids["students"][0]], "unknown_count": 1,
    }
    with patch.object(sessions_router, "decode_image", return_value=object()), \
         patch.object(sessions_router, "detect_faces", return_value=[object(), object()]), \
         patch.object(sessions_router, "extract_embedding", return_value=[0.0] * 512), \
         patch.object(sessions_router, "estimate_yaw", return_value=0), \
         patch.object(sessions_router, "classify_pose_angle", return_value="front"), \
         patch.object(sessions_router, "match_faces_against_roster", return_value=match):
        response = api.post(f"/api/sessions/{opened['id']}/recognize", files={"photos": ("x.jpg", b"image", "image/jpeg")})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["recognized_students"][0]["student_id"] == ids["students"][0]
    assert [s["id"] for s in data["absent_students"]] == [ids["students"][1]]
    assert data["unknown_faces_count"] == 1


def test_commit_attendance_and_close(client):
    api, _, testing_session, ids = client
    opened = api.post(f"/api/courses/{ids['course']}/sessions").json()
    payload = {"records": [
        {"student_id": ids["students"][0], "status": "present", "source": "manual", "confidence": 0.9},
        {"student_id": ids["students"][1], "status": "absent", "source": "manual"},
    ]}
    response = api.put(f"/api/sessions/{opened['id']}/attendance", json=payload)
    assert response.status_code == 200, response.text
    assert len(response.json()) == 2
    with testing_session() as db:
        assert db.get(models.Session, opened["id"]).status == "closed"
        assert db.query(models.AttendanceRecord).filter_by(session_id=opened["id"]).count() == 2
    assert api.put(f"/api/sessions/{opened['id']}/attendance", json=payload).status_code == 400


def test_commit_rejects_students_outside_roster(client):
    api, _, _, ids = client
    opened = api.post(f"/api/courses/{ids['course']}/sessions").json()
    response = api.put(f"/api/sessions/{opened['id']}/attendance", json={"records": [
        {"student_id": 999, "status": "present", "source": "manual"},
    ]})
    assert response.status_code == 400
