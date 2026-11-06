"""API tests for course attendance reports and CSV exports."""

from datetime import datetime, timezone

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
    from backend.app.routers.reports import router
except ModuleNotFoundError:
    from app import models
    from app.auth import get_current_user
    from app.db import get_db
    from app.routers.reports import router


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
        db.flush()
        closed_one = models.Session(course_id=course.id, status="closed")
        closed_two = models.Session(course_id=course.id, status="closed")
        db.add_all([closed_one, closed_two, models.Session(course_id=course.id, status="open")])
        db.flush()
        db.add_all([
            models.AttendanceRecord(session_id=closed_one.id, student_id=students[0].id, status="present", source="manual"),
            models.AttendanceRecord(session_id=closed_two.id, student_id=students[0].id, status="absent", source="manual"),
            models.AttendanceRecord(session_id=closed_one.id, student_id=students[1].id, status="present", source="manual"),
            models.AttendanceRecord(session_id=closed_two.id, student_id=students[1].id, status="present", source="manual"),
        ])
        db.commit()
        ids = {"admin": admin.id, "lecturer": lecturer.id, "other": other.id, "course": course.id}

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


def test_get_course_report_success(client):
    api, _, _, ids = client
    response = api.get(f"/api/courses/{ids['course']}/report")
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["total_sessions"] == 2
    assert [(s["student_code"], s["attended_sessions"], s["attendance_percentage"]) for s in report["students"]] == [
        ("S001", 1, 50.0), ("S002", 2, 100.0)
    ]


def test_get_course_report_zero_sessions(client):
    api, _, testing_session, ids = client
    with testing_session() as db:
        db.query(models.Session).filter_by(course_id=ids["course"]).delete()
        db.commit()
    response = api.get(f"/api/courses/{ids['course']}/report")
    assert response.status_code == 200
    assert response.json()["total_sessions"] == 0
    assert all(s["attendance_percentage"] == 0.0 for s in response.json()["students"])


def test_get_course_report_forbidden(client):
    api, app, _, ids = client
    app.state.user_id = ids["other"]
    response = api.get(f"/api/courses/{ids['course']}/report")
    assert response.status_code == 403


def test_get_course_report_not_found(client):
    api, _, _, _ = client
    assert api.get("/api/courses/999/report").status_code == 404


def test_get_course_report_csv(client):
    api, _, _, ids = client
    response = api.get(f"/api/courses/{ids['course']}/report/csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert 'filename="attendance_report_CS101.csv"' in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")
    text = response.content.decode("utf-8-sig")
    assert "Student Code,Full Name,Total Sessions,Attended Sessions,Attendance Rate (%)" in text
    assert "S001,Student 1,2,1,50.0" in text


def test_admin_access_any_course_report(client):
    api, app, _, ids = client
    app.state.user_id = ids["admin"]
    response = api.get(f"/api/courses/{ids['course']}/report")
    assert response.status_code == 200
    assert response.json()["course_code"] == "CS101"
