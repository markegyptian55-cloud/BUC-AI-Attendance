"""Behavioral tests for roster-scoped face matching and its vector cache."""

import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Support both ``pytest backend/tests`` at the repository root and
# ``pytest tests`` from the backend directory.
current_dir = Path(__file__).resolve().parent
backend_dir = current_dir.parent
project_root = backend_dir.parent
for p in [str(project_root), str(backend_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# These tests exercise only deterministic vector utilities. Avoid importing
# InsightFace's optional native/model stack during test collection.
if "insightface.app" not in sys.modules:
    insightface_module = ModuleType("insightface")
    insightface_module.__path__ = []
    insightface_app_module = ModuleType("insightface.app")
    insightface_app_module.FaceAnalysis = type("FaceAnalysis", (), {})
    insightface_module.app = insightface_app_module
    sys.modules["insightface"] = insightface_module
    sys.modules["insightface.app"] = insightface_app_module

from backend.app.db import Base
from backend.app.models import FaceEmbedding, Student
from backend.app.services.matcher import (
    VectorCache,
    match_faces_against_roster,
    vector_cache,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _unit_vector(first_coordinate: float = 1.0) -> np.ndarray:
    """Build a normalized 512-vector whose first component is controlled."""
    vector = np.zeros(512, dtype=np.float32)
    vector[0] = first_coordinate
    vector[1] = np.sqrt(max(0.0, 1.0 - first_coordinate**2))
    return vector


def _add_student(db_session, student_code: str, vector: np.ndarray, angle="front"):
    student = Student(
        student_code=student_code,
        full_name=f"Student {student_code}",
        level="1",
        group_name="A",
        consent_at=datetime(2025, 1, 1),
    )
    db_session.add(student)
    db_session.flush()
    db_session.add(
        FaceEmbedding(
            student_id=student.id,
            vector=np.asarray(vector, dtype=np.float32).tobytes(),
            angle=angle,
        )
    )
    db_session.commit()
    return student


def _match(db_session, query, roster_ids, angle="front"):
    # Matching intentionally uses a process-wide cache; refresh it between
    # independent in-memory databases used by these unit tests.
    vector_cache.invalidate()
    return match_faces_against_roster(
        [{"embedding": query, "angle": angle}], roster_ids, db_session
    )


def test_exact_match(db_session):
    enrolled = _unit_vector()
    student = _add_student(db_session, "S1", enrolled)

    result = _match(db_session, enrolled, [student.id])

    assert result["recognized"][0]["student_id"] == student.id
    assert result["recognized"][0]["confidence"] == 1.0
    assert result["recognized"][0]["status"] == "present"
    assert result["unknown_count"] == 0


def test_partial_match_above_threshold(db_session):
    student = _add_student(db_session, "S1", _unit_vector())

    result = _match(db_session, _unit_vector(0.65), [student.id])

    assert result["recognized"][0]["confidence"] == pytest.approx(0.65, abs=1e-4)
    assert result["recognized"][0]["status"] == "present"


def test_stranger_below_threshold_is_unknown(db_session):
    student = _add_student(db_session, "S1", _unit_vector())

    result = _match(db_session, _unit_vector(0.40), [student.id])

    assert result["recognized"] == []
    assert result["unknown_count"] == 1


def test_roster_boundary_rejects_non_roster_student(db_session):
    roster_student = _add_student(db_session, "S1", _unit_vector(0.0))
    non_roster_student = _add_student(db_session, "S2", _unit_vector())

    result = _match(db_session, _unit_vector(0.99), [roster_student.id])

    assert result["recognized"] == []
    assert result["matched_student_ids"] == []
    assert result["unknown_count"] == 1
    assert non_roster_student.id not in result["matched_student_ids"]


def test_greedy_one_to_one_prevents_duplicate_assignment(db_session):
    student = _add_student(db_session, "S1", _unit_vector())
    queries = [
        {"embedding": _unit_vector(0.80), "angle": "front"},
        {"embedding": _unit_vector(0.95), "angle": "front"},
    ]

    vector_cache.invalidate()
    result = match_faces_against_roster(queries, [student.id], db_session)

    assert len(result["recognized"]) == 1
    assert result["recognized"][0]["query_index"] == 1
    assert result["recognized"][0]["confidence"] == pytest.approx(0.95, abs=1e-4)
    assert result["unknown_count"] == 1


def test_dual_threshold_front_vs_side(db_session):
    student = _add_student(db_session, "S1", _unit_vector())
    query = _unit_vector(0.58)

    front_result = _match(db_session, query, [student.id], angle="front")
    side_result = _match(db_session, query, [student.id], angle="left")

    assert front_result["recognized"] == []
    assert front_result["unknown_count"] == 1
    assert side_result["recognized"][0]["student_id"] == student.id
    assert side_result["unknown_count"] == 0


def test_empty_query_faces(db_session):
    result = match_faces_against_roster([], [1], db_session)

    assert result["recognized"] == []
    assert result["unknown_count"] == 0


def test_empty_roster(db_session):
    queries = [
        {"embedding": _unit_vector(), "angle": "front"},
        {"embedding": _unit_vector(0.7), "angle": "left"},
    ]

    result = match_faces_against_roster(queries, [], db_session)

    assert result["recognized"] == []
    assert result["unknown_count"] == len(queries)


def test_vector_cache_load_and_invalidation(db_session):
    student = _add_student(db_session, "S1", _unit_vector(2.0))
    cache = VectorCache()
    cache._ensure_loaded(db_session)

    items, matrix = cache.get_roster_vectors([student.id])

    assert matrix.shape == (1, 512)
    assert matrix.dtype == np.float32
    assert np.linalg.norm(matrix[0]) == pytest.approx(1.0, abs=1e-6)
    assert items[0]["student_id"] == student.id
    assert cache._dirty is False

    second = _add_student(db_session, "S2", _unit_vector(0.0))
    stale_items, _ = cache.get_roster_vectors([second.id])
    assert stale_items == []

    cache.invalidate()
    refreshed_items, refreshed_matrix = cache.get_roster_vectors([second.id])
    assert cache._dirty is False
    assert [item["student_id"] for item in refreshed_items] == [second.id]
    assert refreshed_matrix.shape == (1, 512)
