"""Unit tests for the Streamlit-facing HTTP API client."""

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "frontend"))
import api_client as client_module  # noqa: E402
from api_client import ApiClient, ApiError  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    # Exercise the non-Streamlit fallback so tests don't depend on an active app runtime.
    monkeypatch.setattr(client_module, "st", None)
    return ApiClient("http://backend")


def response(status=200, payload=None, content=b""):
    result = Mock()
    result.status_code = status
    result.content = content
    result.json.return_value = payload if payload is not None else {}
    return result


def test_login_stores_token_and_user(client, monkeypatch):
    monkeypatch.setattr(client_module.requests, "request", Mock(side_effect=[
        response(payload={"access_token": "secret-token", "token_type": "bearer"}),
        response(payload={"id": 3, "username": "admin", "full_name": "Admin User", "role": "admin"}),
    ]))
    user = client.login("admin", "admin123")
    assert client._token == "secret-token"
    assert client._user == user
    assert user["role"] == "admin"
    assert client_module.requests.request.call_args_list[1].kwargs["headers"]["Authorization"] == "Bearer secret-token"


def test_authenticated_headers(client, monkeypatch):
    client._token = "abc"
    request = Mock(return_value=response(payload=[]))
    monkeypatch.setattr(client_module.requests, "request", request)
    client.list_courses()
    assert request.call_args.kwargs["headers"] == {"Authorization": "Bearer abc"}


@pytest.mark.parametrize(("detail", "expected"), [
    ("Not allowed", "Not allowed"),
    ([{"loc": ["body", "username"], "msg": "Field required", "type": "missing"}], "Field required"),
])
def test_api_error_formatting(client, monkeypatch, detail, expected):
    monkeypatch.setattr(client_module.requests, "request", Mock(return_value=response(400, {"detail": detail})))
    with pytest.raises(ApiError) as error:
        client.get_health()
    assert error.value.status_code == 400
    assert error.value.message == expected


def test_logout_clears_state(client):
    client._token = "token"
    client._user = {"username": "admin"}
    client.logout()
    assert not client.is_authenticated()
    assert client.get_current_user() is None


def test_report_csv_returns_bytes(client, monkeypatch):
    monkeypatch.setattr(client_module.requests, "request", Mock(return_value=response(content=b"course,attendance\n")))
    result = client.get_course_report_csv(4)
    assert result == b"course,attendance\n"
    assert isinstance(result, bytes)


def test_connection_error_is_translated(client, monkeypatch):
    monkeypatch.setattr(client_module.requests, "request", Mock(side_effect=client_module.requests.exceptions.ConnectionError()))
    with pytest.raises(ApiError) as error:
        client.get_health()
    assert error.value.status_code == 503
    assert "FastAPI is running on port 8000" in error.value.message

