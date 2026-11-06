"""API tests for biometric face quality, enrollment, and revocation routes."""

from datetime import datetime, timezone

import cv2
import numpy as np
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
    from backend.app.routers import faces as faces_router
    from backend.app.schemas import FaceCheckResult
except ModuleNotFoundError:
    from app import models
    from app.auth import get_current_user
    from app.db import get_db
    from app.routers import faces as faces_router
    from app.schemas import FaceCheckResult


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
    app.include_router(faces_router.router)

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


def image_bytes():
    image = np.full((160, 160, 3), 127, dtype=np.uint8)
    # Add texture so the generated image is a plausible quality-check input.
    image[::2, ::2] = 230
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def make_student(testing_session):
    with testing_session() as db:
        student = models.Student(
            student_code="S001",
            full_name="Amina Hassan",
            level="2",
            group_name="A",
            consent_at=datetime.now(timezone.utc),
        )
        db.add(student)
        db.commit()
        return student.id


def valid_result():
    return FaceCheckResult(
        face_detected=True,
        face_count=1,
        size_ok=True,
        blur_ok=True,
        brightness_ok=True,
        angle="front",
        is_valid=True,
        message="Face quality check passed",
    )


def test_face_check_returns_quality_result(client, monkeypatch):
    api, _, _ = client
    monkeypatch.setattr(faces_router, "check_image_quality", lambda image, target_angle=None: valid_result())
    response = api.post(
        "/api/faces/check",
        files={"file": ("face.jpg", image_bytes(), "image/jpeg")},
        data={"target_angle": "front"},
    )
    assert response.status_code == 200
    assert response.json()["is_valid"] is True
    assert response.json()["angle"] == "front"


def test_enrollment_saves_three_embeddings_and_invalidates_cache(client, monkeypatch):
    api, _, testing_session = client
    student_id = make_student(testing_session)
    monkeypatch.setattr(faces_router, "check_image_quality", lambda image, target_angle=None: valid_result())
    monkeypatch.setattr(faces_router, "detect_faces", lambda image: [object()])
    monkeypatch.setattr(faces_router, "extract_embedding", lambda face: np.ones(512, dtype=np.float32) / np.sqrt(512))
    invalidated = []
    monkeypatch.setattr(faces_router.vector_cache, "invalidate", lambda: invalidated.append(True))
    payload = {f"{angle}_photo": (f"{angle}.jpg", image_bytes(), "image/jpeg") for angle in ("front", "left", "right")}

    response = api.post(f"/api/students/{student_id}/faces", files=payload)
    assert response.status_code == 200, response.text
    assert response.json()["enrolled_count"] == 3
    assert invalidated == [True]
    with testing_session() as db:
        stored = db.query(models.FaceEmbedding).filter_by(student_id=student_id).all()
        assert len(stored) == 3
        assert {row.angle for row in stored} == {"front", "left", "right"}
        assert all(len(row.vector) == 2048 for row in stored)


def test_invalid_enrollment_photo_leaves_database_unchanged(client, monkeypatch):
    api, _, testing_session = client
    student_id = make_student(testing_session)
    with testing_session() as db:
        db.add(models.FaceEmbedding(student_id=student_id, vector=b"existing", angle="front"))
        db.commit()
    calls = []

    def quality(image, target_angle=None):
        calls.append(target_angle)
        result = valid_result()
        if target_angle == "left":
            result.is_valid = False
            result.message = "pose mismatch"
        return result

    monkeypatch.setattr(faces_router, "check_image_quality", quality)
    monkeypatch.setattr(faces_router, "detect_faces", lambda image: [object()])
    monkeypatch.setattr(faces_router, "extract_embedding", lambda face: np.ones(512, dtype=np.float32) / np.sqrt(512))
    payload = {f"{angle}_photo": (f"{angle}.jpg", image_bytes(), "image/jpeg") for angle in ("front", "left", "right")}
    response = api.post(f"/api/students/{student_id}/faces", files=payload)
    assert response.status_code == 400
    assert "Enrollment rejected for left photo" in response.json()["detail"]
    assert calls == ["front", "left"]
    with testing_session() as db:
        rows = db.query(models.FaceEmbedding).filter_by(student_id=student_id).all()
        assert len(rows) == 1
        assert rows[0].vector == b"existing"


def test_delete_revokes_all_embeddings(client, monkeypatch):
    api, _, testing_session = client
    student_id = make_student(testing_session)
    with testing_session() as db:
        db.add_all([
            models.FaceEmbedding(student_id=student_id, vector=b"a", angle="front"),
            models.FaceEmbedding(student_id=student_id, vector=b"b", angle="left"),
        ])
        db.commit()
    invalidated = []
    monkeypatch.setattr(faces_router.vector_cache, "invalidate", lambda: invalidated.append(True))
    response = api.delete(f"/api/students/{student_id}/faces")
    assert response.status_code == 200
    assert response.json()["deleted_count"] == 2
    assert invalidated == [True]
    with testing_session() as db:
        assert db.query(models.FaceEmbedding).filter_by(student_id=student_id).count() == 0


def test_non_admin_cannot_check_enroll_or_revoke(client):
    api, app, testing_session = client
    student_id = make_student(testing_session)
    app.state.test_role = "lecturer"
    upload = {"file": ("face.jpg", image_bytes(), "image/jpeg")}
    assert api.post("/api/faces/check", files=upload).status_code == 403
    payload = {f"{angle}_photo": (f"{angle}.jpg", image_bytes(), "image/jpeg") for angle in ("front", "left", "right")}
    assert api.post(f"/api/students/{student_id}/faces", files=payload).status_code == 403
    assert api.delete(f"/api/students/{student_id}/faces").status_code == 403
