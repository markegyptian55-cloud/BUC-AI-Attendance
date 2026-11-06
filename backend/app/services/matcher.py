"""Roster-scoped face embedding cache and 1-to-1 matcher."""

from typing import Any, Collection, Dict, List, Optional, Set, Tuple
import threading

import numpy as np
from sqlalchemy.orm import Session

try:
    from ..config import settings
    from ..models import Student, FaceEmbedding
    from .face_engine import bytes_to_embedding
except (ImportError, ValueError):
    try:
        from backend.app.config import settings
        from backend.app.models import Student, FaceEmbedding
        from backend.app.services.face_engine import bytes_to_embedding
    except ModuleNotFoundError:
        from app.config import settings
        from app.models import Student, FaceEmbedding
        from app.services.face_engine import bytes_to_embedding


_EMBEDDING_SIZE = 512
_VECTOR_EPSILON = 1e-10


class VectorCache:
    """Thread-safe process cache of normalized enrolled face vectors."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: List[Dict[str, Any]] = []
        self._dirty = True
        # Kept only to make invalidate() refresh on the next cache read. The
        # matching entry point also supplies its current session on refresh.
        self._db: Optional[Session] = None

    def load_from_db(self, db: Session) -> None:
        """Load all student embeddings and normalize them as float32 vectors."""
        with self._lock:
            rows = (
                db.query(FaceEmbedding, Student)
                .join(Student, FaceEmbedding.student_id == Student.id)
                .all()
            )

            items: List[Dict[str, Any]] = []
            for embedding, student in rows:
                try:
                    vector = np.asarray(
                        bytes_to_embedding(embedding.vector), dtype=np.float32
                    ).reshape(-1)
                except (TypeError, ValueError):
                    # A corrupt or legacy BLOB must not poison the entire cache.
                    continue

                norm = float(np.linalg.norm(vector))
                if vector.size != _EMBEDDING_SIZE or not np.isfinite(norm) or norm <= _VECTOR_EPSILON:
                    continue

                vector = np.ascontiguousarray(vector / norm, dtype=np.float32)
                items.append(
                    {
                        "student_id": int(student.id),
                        "student_code": str(student.student_code),
                        "full_name": str(student.full_name),
                        "angle": str(embedding.angle),
                        "vector": vector,
                    }
                )

            self._items = items
            self._db = db
            self._dirty = False

    def invalidate(self) -> None:
        """Mark cached vectors stale; the next read reloads the database."""
        with self._lock:
            self._dirty = True

    def _ensure_loaded(self, db: Optional[Session] = None) -> None:
        # Hold the lock through the query so concurrent callers cannot each
        # issue a redundant refresh. load_from_db uses the same lock, so inline
        # its body here by checking and releasing before calling it.
        with self._lock:
            needs_load = self._dirty
            active_db = db if db is not None else self._db
        if needs_load and active_db is not None:
            self.load_from_db(active_db)

    def get_roster_vectors(
        self, roster_student_ids: Collection[int]
    ) -> Tuple[List[Dict[str, Any]], np.ndarray]:
        """Return only roster embeddings and their row-stacked matrix."""
        self._ensure_loaded()
        roster_ids = set(roster_student_ids)
        with self._lock:
            items = [
                item for item in self._items if item["student_id"] in roster_ids
            ]
            # Copy the list and vectors' stack while locked to keep callers
            # isolated from a simultaneous cache refresh.
            roster_items = [dict(item) for item in items]

        if not roster_items:
            return [], np.empty((0, _EMBEDDING_SIZE), dtype=np.float32)
        matrix = np.ascontiguousarray(
            np.stack([item["vector"] for item in roster_items]).astype(
                np.float32, copy=False
            )
        )
        return roster_items, matrix


vector_cache = VectorCache()


def match_faces_against_roster(
    query_faces: List[Dict[str, Any]],
    roster_student_ids: Collection[int],
    db: Session,
    front_threshold: Optional[float] = None,
    side_threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """Match query faces to distinct students in the active course roster."""
    if not query_faces:
        return {"recognized": [], "unknown_count": 0, "matched_student_ids": []}

    if not roster_student_ids:
        return {
            "recognized": [],
            "unknown_count": len(query_faces),
            "matched_student_ids": [],
        }

    active_front_threshold = (
        settings.MATCH_THRESHOLD if front_threshold is None else front_threshold
    )
    active_side_threshold = (
        settings.SIDE_MATCH_THRESHOLD if side_threshold is None else side_threshold
    )

    # Supply the current request session when the cache is stale, avoiding a
    # refresh through a session retained from a prior request.
    vector_cache._ensure_loaded(db)
    roster_items, roster_matrix = vector_cache.get_roster_vectors(
        roster_student_ids
    )
    if not roster_items:
        return {
            "recognized": [],
            "unknown_count": len(query_faces),
            "matched_student_ids": [],
        }

    query_matrix = np.stack(
        [np.asarray(face["embedding"], dtype=np.float32).reshape(-1) for face in query_faces]
    )
    if query_matrix.ndim != 2 or query_matrix.shape[1] != _EMBEDDING_SIZE:
        raise ValueError("Each query embedding must contain exactly 512 values")
    query_matrix = query_matrix / (
        np.linalg.norm(query_matrix, axis=1, keepdims=True) + _VECTOR_EPSILON
    )

    similarities = np.dot(query_matrix, roster_matrix.T)
    candidates = [
        (float(similarities[query_index, roster_index]), query_index, roster_index)
        for query_index in range(similarities.shape[0])
        for roster_index in range(similarities.shape[1])
    ]
    candidates.sort(key=lambda candidate: candidate[0], reverse=True)

    matched_queries: Set[int] = set()
    matched_students: Set[int] = set()
    recognized: List[Dict[str, Any]] = []

    for score, query_index, roster_index in candidates:
        if query_index in matched_queries:
            continue

        roster_item = roster_items[roster_index]
        student_id = roster_item["student_id"]
        if student_id in matched_students:
            continue

        query_angle = query_faces[query_index].get("angle", "front")
        roster_angle = roster_item["angle"]
        is_side = query_angle in ("left", "right") or roster_angle in (
            "left",
            "right",
        )
        threshold = active_side_threshold if is_side else active_front_threshold
        if score < threshold:
            continue

        matched_queries.add(query_index)
        matched_students.add(student_id)
        recognized.append(
            {
                "student_id": student_id,
                "student_code": roster_item["student_code"],
                "full_name": roster_item["full_name"],
                "confidence": round(score, 4),
                "query_index": query_index,
                "matched_angle": roster_angle,
                "query_angle": query_angle,
                "status": "present",
            }
        )

    return {
        "recognized": recognized,
        "unknown_count": len(query_faces) - len(matched_queries),
        "matched_student_ids": list(matched_students),
    }
