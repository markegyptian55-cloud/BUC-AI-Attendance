from unittest.mock import patch

from fastapi.testclient import TestClient

try:
    from backend.app import main
except ModuleNotFoundError:
    from app import main


def test_root_endpoint():
    response = TestClient(main.app).get("/")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Attendance AI API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }


def test_health_endpoint_via_lifespan():
    with (
        patch.object(main.Base.metadata, "create_all"),
        patch.object(main, "get_face_engine", return_value=object()),
        patch.object(main.vector_cache, "load_from_db"),
        TestClient(main.app) as client,
    ):
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["model_loaded"] is True
    assert response.json()["database"] == "ok"


def test_cors_preflight():
    with TestClient(main.app) as client:
        response = client.options(
            "/api/auth/login",
            headers={
                "Origin": "http://localhost:8501",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8501"


def test_openapi_schema_contains_all_routes():
    with TestClient(main.app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    expected_paths = {
        "/api/auth/login",
        "/api/students",
        "/api/faces/check",
        "/api/courses",
        "/api/courses/{course_id}/sessions",
        "/api/courses/{course_id}/report",
    }
    assert expected_paths <= paths.keys()
