"""API tests for course and roster management routes."""

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
    from backend.app.routers.courses import router
except ModuleNotFoundError:
    from app import models
    from app.auth import get_current_user
    from app.db import get_db
    from app.routers.courses import router


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False)
    with testing_session() as db:
        admin = models.User(username="admin", hashed_password="unused", full_name="Admin User", role="admin")
        lecturer_one = models.User(username="lecturer1", hashed_password="unused", full_name="Lecturer One", role="lecturer")
        lecturer_two = models.User(username="lecturer2", hashed_password="unused", full_name="Lecturer Two", role="lecturer")
        db.add_all([admin, lecturer_one, lecturer_two])
        db.flush()
        users = {"admin": admin.id, "lecturer1": lecturer_one.id, "lecturer2": lecturer_two.id}
        db.commit()

    app = FastAPI()
    app.include_router(router)

    def override_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.state.user_id = users["admin"]

    def current_user():
        with testing_session() as db:
            return db.query(models.User).filter_by(id=app.state.user_id).one()

    app.dependency_overrides[get_current_user] = current_user
    with TestClient(app) as test_client:
        yield test_client, app, testing_session, users
    models.Base.metadata.drop_all(engine)
    engine.dispose()


def create_payload(**overrides):
    return {"code": "CS101", "name": "Introduction to Computing", "lecturer_id": 2, **overrides}


def add_student(db, code):
    student = models.Student(
        student_code=code, full_name=f"Student {code}", level="2", group_name="A",
        consent_at=datetime.now(timezone.utc),
    )
    db.add(student)
    db.commit()
    return student.id


def test_admin_creates_course_with_lecturer_and_count(client):
    api, _, _, _ = client
    response = api.post("/api/courses", json=create_payload())
    assert response.status_code == 200
    assert response.json()["lecturer_name"] == "Lecturer One"
    assert response.json()["student_count"] == 0


def test_duplicate_course_code_returns_400(client):
    api, _, _, _ = client
    assert api.post("/api/courses", json=create_payload()).status_code == 200
    assert api.post("/api/courses", json=create_payload(name="Duplicate")).status_code == 400


def test_nonexistent_lecturer_returns_400(client):
    api, _, _, _ = client
    assert api.post("/api/courses", json=create_payload(lecturer_id=999)).status_code == 400


def test_roster_replacement_and_invalid_student(client):
    api, _, testing_session, _ = client
    course_id = api.post("/api/courses", json=create_payload()).json()["id"]
    with testing_session() as db:
        student_one = add_student(db, "S001")
        student_two = add_student(db, "S002")
    response = api.put(f"/api/courses/{course_id}/students", json={"student_ids": [student_one, student_two, student_one]})
    assert response.status_code == 200
    assert response.json()["student_count"] == 2
    assert api.get(f"/api/courses/{course_id}/students").json()
    invalid = api.put(f"/api/courses/{course_id}/students", json={"student_ids": [student_one, 999]})
    assert invalid.status_code == 400
    roster = api.get(f"/api/courses/{course_id}/students").json()
    assert [item["id"] for item in roster] == [student_one, student_two]


def test_lecturer_access_is_limited_to_owned_course(client):
    api, app, _, users = client
    own_course = api.post("/api/courses", json=create_payload()).json()
    other_course = api.post("/api/courses", json=create_payload(code="CS102", lecturer_id=users["lecturer2"])).json()
    app.state.user_id = users["lecturer1"]
    assert api.get(f"/api/courses/{own_course['id']}/students").status_code == 200
    assert api.get(f"/api/courses/{other_course['id']}/students").status_code == 403
    assert [course["id"] for course in api.get("/api/courses").json()] == [own_course["id"]]


def test_non_admin_cannot_create_or_replace_roster(client):
    api, app, _, users = client
    course = api.post("/api/courses", json=create_payload()).json()
    app.state.user_id = users["lecturer1"]
    assert api.post("/api/courses", json=create_payload(code="CS102")).status_code == 403
    assert api.put(f"/api/courses/{course['id']}/students", json={"student_ids": []}).status_code == 403
