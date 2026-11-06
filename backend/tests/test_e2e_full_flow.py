"""Full API journey using an isolated SQLite database and mocked CV inference."""

from datetime import datetime, timezone

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

try:
    from backend.app import models
    from backend.app.auth import hash_password
    from backend.app.db import get_db
    from backend.app.routers import faces as faces_router
    from backend.app.routers import sessions as sessions_router
    from backend.app.routers import auth, courses, reports, sessions, students
    from backend.app.schemas import FaceCheckResult
except ModuleNotFoundError:
    from app import models
    from app.auth import hash_password
    from app.db import get_db
    from app.routers import faces as faces_router
    from app.routers import sessions as sessions_router
    from app.routers import auth, courses, reports, sessions, students
    from app.schemas import FaceCheckResult


PASSWORD = "e2e-test-password"


@pytest.fixture
def e2e_client(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False)
    with testing_session() as db:
        admin = models.User(username="admin", hashed_password=hash_password(PASSWORD), full_name="BUC Admin", role="admin")
        lecturer = models.User(username="lecturer1", hashed_password=hash_password(PASSWORD), full_name="Lecturer One", role="lecturer")
        other_lecturer = models.User(username="lecturer2", hashed_password=hash_password(PASSWORD), full_name="Lecturer Two", role="lecturer")
        db.add_all([admin, lecturer, other_lecturer])
        db.commit()
        lecturer_id = lecturer.id
        other_lecturer_id = other_lecturer.id

    app = FastAPI()
    for router in (auth.router, students.router, faces_router.router, courses.router, sessions.router, reports.router):
        app.include_router(router)

    def override_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    # Keep the API lifecycle real while substituting only expensive CV operations.
    monkeypatch.setattr(faces_router, "decode_image", lambda content: object())
    monkeypatch.setattr(faces_router, "check_image_quality", lambda image, target_angle=None: FaceCheckResult(
        face_detected=True, face_count=1, size_ok=True, blur_ok=True,
        brightness_ok=True, angle=target_angle or "front", is_valid=True,
        message="Synthetic test face accepted",
    ))
    monkeypatch.setattr(faces_router, "detect_faces", lambda image: [object()])
    monkeypatch.setattr(faces_router, "extract_embedding", lambda face: np.ones(512, dtype=np.float32) / np.sqrt(512))
    monkeypatch.setattr(faces_router, "embedding_to_bytes", lambda vector: vector.tobytes())
    monkeypatch.setattr(faces_router.vector_cache, "invalidate", lambda: None)

    with TestClient(app) as api:
        yield api, testing_session, lecturer_id, other_lecturer_id
    models.Base.metadata.drop_all(engine)
    engine.dispose()


def _login(api, username):
    response = api.post("/api/auth/login-json", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_complete_admin_lecturer_attendance_and_edge_case_flow(e2e_client, monkeypatch):
    api, testing_session, lecturer_id, other_lecturer_id = e2e_client

    admin_headers = _login(api, "admin")
    lecturer_headers = _login(api, "lecturer1")

    # Admin registers the students and enrolls synthetic front/side pose embeddings.
    student_one_response = api.post("/api/students", headers=admin_headers, json={
        "student_code": "BUC-E2E-01", "full_name": "Mohamed Mostafa",
        "level": "3", "group_name": "A", "consent": True,
    })
    assert student_one_response.status_code == 200, student_one_response.text
    student_one = student_one_response.json()
    student_two_response = api.post("/api/students", headers=admin_headers, json={
        "student_code": "BUC-E2E-02", "full_name": "Sara Ahmed",
        "level": "3", "group_name": "A", "consent": True,
    })
    assert student_two_response.status_code == 200, student_two_response.text
    student_two = student_two_response.json()
    directory = api.get("/api/students", headers=admin_headers)
    assert directory.status_code == 200
    assert {item["student_code"] for item in directory.json()} >= {"BUC-E2E-01", "BUC-E2E-02"}

    enroll = api.post(
        f"/api/students/{student_one['id']}/faces", headers=admin_headers,
        files={f"{angle}_photo": (f"{angle}.jpg", b"synthetic-{angle}", "image/jpeg")
               for angle in ("front", "left", "right")},
    )
    assert enroll.status_code == 200, enroll.text
    assert enroll.json()["enrolled_count"] == 3
    with testing_session() as db:
        poses = db.query(models.FaceEmbedding).filter_by(student_id=student_one["id"]).all()
        assert {pose.angle for pose in poses} == {"front", "left", "right"}

    course_response = api.post("/api/courses", headers=admin_headers, json={
        "code": "CS401", "name": "Computer Vision in Production", "lecturer_id": lecturer_id,
    })
    assert course_response.status_code == 200, course_response.text
    course = course_response.json()
    roster = api.put(f"/api/courses/{course['id']}/students", headers=admin_headers,
                     json={"student_ids": [student_one["id"], student_two["id"]]})
    assert roster.status_code == 200, roster.text

    # Lecturer sees the assigned course, starts a session, and reviews recognition output.
    visible = api.get("/api/courses", headers=lecturer_headers)
    assert visible.status_code == 200
    assert [item["code"] for item in visible.json()] == ["CS401"]
    opened = api.post(f"/api/courses/{course['id']}/sessions", headers=lecturer_headers)
    assert opened.status_code == 200, opened.text
    session_id = opened.json()["id"]
    assert opened.json()["status"] == "open"

    recognition = {
        "recognized": [{"student_id": student_one["id"], "student_code": "BUC-E2E-01",
                         "full_name": "Mohamed Mostafa", "confidence": 0.93}],
        "matched_student_ids": [student_one["id"]], "unknown_count": 1,
    }
    monkeypatch.setattr(sessions_router, "decode_image", lambda content: object())
    monkeypatch.setattr(sessions_router, "detect_faces", lambda image: [object(), object()])
    monkeypatch.setattr(sessions_router, "extract_embedding", lambda face: np.ones(512, dtype=np.float32) / np.sqrt(512))
    monkeypatch.setattr(sessions_router, "estimate_yaw", lambda face: 0)
    monkeypatch.setattr(sessions_router, "classify_pose_angle", lambda yaw: "front")
    monkeypatch.setattr(sessions_router, "match_faces_against_roster", lambda query, roster_ids, db: recognition)
    recognized = api.post(f"/api/sessions/{session_id}/recognize", headers=lecturer_headers,
                          files={"photos": ("classroom.jpg", b"synthetic classroom", "image/jpeg")})
    assert recognized.status_code == 200, recognized.text
    result = recognized.json()
    assert result["recognized_students"][0]["student_code"] == "BUC-E2E-01"
    assert result["recognized_students"][0]["status"] == "present"
    assert [item["student_code"] for item in result["absent_students"]] == ["BUC-E2E-02"]
    assert result["unknown_faces_count"] == 1

    committed = api.put(f"/api/sessions/{session_id}/attendance", headers=lecturer_headers, json={"records": [
        {"student_id": student_one["id"], "status": "present", "source": "auto", "confidence": 0.93},
        {"student_id": student_two["id"], "status": "absent", "source": "manual"},
    ]})
    assert committed.status_code == 200, committed.text
    assert {(row["student_code"], row["status"], row["source"]) for row in committed.json()} == {
        ("BUC-E2E-01", "present", "auto"), ("BUC-E2E-02", "absent", "manual")
    }
    detail = api.get(f"/api/sessions/{session_id}", headers=lecturer_headers)
    assert detail.status_code == 200 and detail.json()["status"] == "closed"
    with testing_session() as db:
        assert db.query(models.AttendanceRecord).filter_by(session_id=session_id).count() == 2

    report_response = api.get(f"/api/courses/{course['id']}/report", headers=lecturer_headers)
    assert report_response.status_code == 200, report_response.text
    report = report_response.json()
    assert report["total_sessions"] == 1
    stats = {item["student_code"]: item for item in report["students"]}
    assert (stats["BUC-E2E-01"]["attended_sessions"], stats["BUC-E2E-01"]["total_sessions"], stats["BUC-E2E-01"]["attendance_percentage"]) == (1, 1, 100.0)
    assert (stats["BUC-E2E-02"]["attended_sessions"], stats["BUC-E2E-02"]["total_sessions"], stats["BUC-E2E-02"]["attendance_percentage"]) == (0, 1, 0.0)
    csv_response = api.get(f"/api/courses/{course['id']}/report/csv", headers=lecturer_headers)
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.headers["content-type"]
    csv_text = csv_response.content.decode("utf-8-sig")
    assert csv_response.content.startswith(b"\xef\xbb\xbf")
    assert "BUC-E2E-01,Mohamed Mostafa,1,1,100.0" in csv_text
    assert "BUC-E2E-02,Sara Ahmed,1,0,0.0" in csv_text

    # Closed-session, roster, access-control, upload-count, and missing-resource defenses.
    closed = api.put(f"/api/sessions/{session_id}/attendance", headers=lecturer_headers,
                     json={"records": [{"student_id": student_one["id"], "status": "present"}]})
    assert closed.status_code == 400 and closed.json()["detail"] == "Session is closed"

    open_again = api.post(f"/api/courses/{course['id']}/sessions", headers=lecturer_headers).json()
    outsider_response = api.post("/api/students", headers=admin_headers, json={
        "student_code": "BUC-E2E-OUT", "full_name": "Outside Student",
        "level": "3", "group_name": "A", "consent": True,
    })
    assert outsider_response.status_code == 200
    outside_commit = api.put(f"/api/sessions/{open_again['id']}/attendance", headers=lecturer_headers,
                             json={"records": [{"student_id": outsider_response.json()["id"], "status": "present"}]})
    assert outside_commit.status_code == 400

    other_course = api.post("/api/courses", headers=admin_headers, json={
        "code": "CS402", "name": "Other Lecturer Course", "lecturer_id": other_lecturer_id,
    }).json()
    other_session = api.post(f"/api/courses/{other_course['id']}/sessions", headers=admin_headers).json()
    assert api.post(f"/api/courses/{other_course['id']}/sessions", headers=lecturer_headers).status_code == 403
    forbidden_commit = api.put(f"/api/sessions/{other_session['id']}/attendance", headers=lecturer_headers,
                               json={"records": []})
    assert forbidden_commit.status_code == 403

    assert api.post(f"/api/sessions/{open_again['id']}/recognize", headers=lecturer_headers).status_code == 400
    six_photos = [("photos", (f"room-{i}.jpg", b"image", "image/jpeg")) for i in range(6)]
    assert api.post(f"/api/sessions/{open_again['id']}/recognize", headers=lecturer_headers, files=six_photos).status_code == 400
    assert api.post("/api/courses/99999/sessions", headers=lecturer_headers).status_code == 404
    assert api.get("/api/courses/99999/report", headers=lecturer_headers).status_code == 404
    assert api.get("/api/sessions/99999", headers=lecturer_headers).status_code == 404
    missing_recognition = api.post("/api/sessions/99999/recognize", headers=lecturer_headers,
                                   files={"photos": ("room.jpg", b"image", "image/jpeg")})
    assert missing_recognition.status_code == 404
