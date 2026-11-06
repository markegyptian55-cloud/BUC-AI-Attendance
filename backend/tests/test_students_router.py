"""API tests for student management routes."""

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
    from backend.app.routers.students import router
except ModuleNotFoundError:
    from app import models
    from app.auth import get_current_user
    from app.db import get_db
    from app.routers.students import router


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False)
    app = FastAPI()
    app.include_router(router)

    def override_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.state.test_role = "admin"

    def current_user():
        return models.User(
            id=1,
            username="tester",
            hashed_password="unused",
            full_name="Test User",
            role=app.state.test_role,
        )

    app.dependency_overrides[get_current_user] = current_user
    with TestClient(app) as test_client:
        yield test_client, app, testing_session
    models.Base.metadata.drop_all(engine)
    engine.dispose()


def student_payload(**overrides):
    return {
        "student_code": "S001",
        "full_name": "Amina Hassan",
        "level": "2",
        "group_name": "A",
        "consent": True,
        **overrides,
    }


def test_create_requires_consent_and_unique_code(client):
    api, _, _ = client
    assert api.post("/api/students", json=student_payload(consent=False)).status_code == 400
    created = api.post("/api/students", json=student_payload())
    assert created.status_code == 200
    assert created.json()["enrolled_faces_count"] == 0
    duplicate = api.post("/api/students", json=student_payload())
    assert duplicate.status_code == 400


def test_list_filters_search_and_counts_enrollments(client):
    api, _, testing_session = client
    student = api.post("/api/students", json=student_payload()).json()
    with testing_session() as db:
        db.add_all([
            models.FaceEmbedding(student_id=student["id"], vector=b"one", angle="front"),
            models.FaceEmbedding(student_id=student["id"], vector=b"two", angle="left"),
        ])
        db.commit()
    listed = api.get("/api/students", params={"search": "amina"}).json()
    assert listed[0]["id"] == student["id"]
    assert listed[0]["enrolled_faces_count"] == 2
    assert api.get("/api/students", params={"level": "2"}).json()[0]["id"] == student["id"]
    assert api.get("/api/students", params={"level": "3"}).json() == []


def test_non_admin_cannot_create_or_delete_and_admin_can_delete(client):
    api, app, testing_session = client
    student = api.post("/api/students", json=student_payload()).json()
    with testing_session() as db:
        db.add(models.FaceEmbedding(student_id=student["id"], vector=b"vector", angle="front"))
        db.commit()
    app.state.test_role = "lecturer"
    assert api.post("/api/students", json=student_payload(student_code="S002")).status_code == 403
    assert api.delete(f"/api/students/{student['id']}").status_code == 403
    app.state.test_role = "admin"
    assert api.delete(f"/api/students/{student['id']}").status_code == 200
    with testing_session() as db:
        assert db.query(models.FaceEmbedding).filter_by(student_id=student["id"]).count() == 0

