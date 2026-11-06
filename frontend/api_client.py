"""Centralized HTTP client for the Attendance AI backend."""

import os
from typing import Optional

import requests

try:
    import streamlit as st
except ImportError:  # Allows this module to be used in non-Streamlit tests/tools.
    st = None


class ApiError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class ApiClient:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or os.getenv("API_URL", "http://127.0.0.1:8000")).rstrip("/")
        self._token: Optional[str] = None
        self._user: Optional[dict] = None

    def _state(self):
        try:
            return st.session_state if st is not None else None
        except Exception:
            return None

    def _get(self, key: str, fallback=None):
        state = self._state()
        try:
            return state.get(key, fallback) if state is not None else getattr(self, f"_{key}", fallback)
        except Exception:
            return getattr(self, f"_{key}", fallback)

    def _set(self, key: str, value) -> None:
        setattr(self, f"_{key}", value)
        state = self._state()
        if state is not None:
            try:
                state[key] = value
            except Exception:
                pass

    def _clear(self, key: str) -> None:
        setattr(self, f"_{key}", None)
        state = self._state()
        if state is not None:
            try:
                state.pop(key, None)
            except Exception:
                pass

    def _request(self, method: str, path: str, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        token = self._get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = requests.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
        except requests.exceptions.ConnectionError as exc:
            raise ApiError("Cannot connect to backend server. Make sure FastAPI is running on port 8000.", 503) from exc
        if response.status_code >= 400:
            detail = None
            try:
                detail = response.json().get("detail")
            except (ValueError, AttributeError, TypeError):
                pass
            if isinstance(detail, list):
                detail = "; ".join(
                    str(item.get("msg", item) if isinstance(item, dict) else item) for item in detail
                )
            message = detail if isinstance(detail, str) and detail else f"Request failed ({response.status_code})."
            raise ApiError(message, response.status_code)
        return response

    def _json(self, method: str, path: str, **kwargs):
        response = self._request(method, path, **kwargs)
        return response.json()

    def login(self, username: str, password: str) -> dict:
        result = self._json("POST", "/api/auth/login-json", json={"username": username, "password": password})
        self._set("token", result["access_token"])
        try:
            user = self._json("GET", "/api/auth/me")
        except Exception:
            self.logout()
            raise
        self._set("user", user)
        return user

    def logout(self) -> None:
        self._clear("token")
        self._clear("user")

    def is_authenticated(self) -> bool:
        return bool(self._get("token"))

    def get_current_user(self) -> Optional[dict]:
        return self._get("user")

    def get_health(self) -> dict: return self._json("GET", "/api/health")
    def list_students(self, search: Optional[str] = None) -> list:
        return self._json("GET", "/api/students", params={"search": search} if search else None)
    def create_student(self, student_code: str, full_name: str, level: str, group_name: str, consent: bool = True) -> dict:
        return self._json("POST", "/api/students", json={"student_code": student_code, "full_name": full_name, "level": level, "group_name": group_name, "consent": consent})
    def delete_student(self, student_id: int) -> dict: return self._json("DELETE", f"/api/students/{student_id}")
    def check_face_photo(self, photo_bytes: bytes, filename: str = "check.jpg") -> dict:
        return self._json("POST", "/api/faces/check", files={"file": (filename, photo_bytes, "image/jpeg")})
    def enroll_student_faces(self, student_id: int, front_bytes: bytes, left_bytes: bytes, right_bytes: bytes) -> dict:
        files = {name: (f"{name}.jpg", data, "image/jpeg") for name, data in (("front_photo", front_bytes), ("left_photo", left_bytes), ("right_photo", right_bytes))}
        return self._json("POST", f"/api/students/{student_id}/faces", files=files)
    def clear_student_faces(self, student_id: int) -> dict: return self._json("DELETE", f"/api/students/{student_id}/faces")
    def list_courses(self) -> list: return self._json("GET", "/api/courses")
    def create_course(self, code: str, name: str, lecturer_id: int) -> dict:
        return self._json("POST", "/api/courses", json={"code": code, "name": name, "lecturer_id": lecturer_id})
    def get_course_students(self, course_id: int) -> list: return self._json("GET", f"/api/courses/{course_id}/students")
    def update_course_roster(self, course_id: int, student_ids: list[int]) -> list:
        return self._json("PUT", f"/api/courses/{course_id}/students", json={"student_ids": student_ids})
    def open_session(self, course_id: int) -> dict: return self._json("POST", f"/api/courses/{course_id}/sessions")
    def list_sessions(self, course_id: int) -> list: return self._json("GET", f"/api/courses/{course_id}/sessions")
    def get_session(self, session_id: int) -> dict: return self._json("GET", f"/api/sessions/{session_id}")
    def recognize_faces(self, session_id: int, photo_files: list[tuple[str, bytes, str]]) -> dict:
        return self._json("POST", f"/api/sessions/{session_id}/recognize", files=[("photos", item) for item in photo_files])
    def commit_attendance(self, session_id: int, records: list[dict]) -> list:
        return self._json("PUT", f"/api/sessions/{session_id}/attendance", json={"records": records})
    def get_course_report(self, course_id: int) -> dict: return self._json("GET", f"/api/courses/{course_id}/report")
    def get_course_report_csv(self, course_id: int) -> bytes:
        return self._request("GET", f"/api/courses/{course_id}/report/csv").content


api = ApiClient()
