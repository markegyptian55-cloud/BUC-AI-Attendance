"""InsightFace loading and image/embedding utilities.

The model is initialized lazily once per process. Callers can load it during
application startup and pass the engine to detection functions, or rely on
``detect_faces`` to retrieve the shared instance.
"""

from typing import Any, List, Optional, Tuple
import threading

import cv2
import numpy as np
from insightface.app import FaceAnalysis

try:
    from ..config import settings
except (ImportError, ValueError):
    try:
        from backend.app.config import settings
    except ModuleNotFoundError:
        from app.config import settings


_engine_lock = threading.Lock()
_engine_instance: Optional[FaceAnalysis] = None


def get_face_engine() -> FaceAnalysis:
    """Return the process-wide, lazily initialized buffalo_l engine."""
    global _engine_instance

    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                app = FaceAnalysis(
                    name="buffalo_l", providers=["CPUExecutionProvider"]
                )
                det_size = getattr(settings, "DET_SIZE", 320)
                app.prepare(ctx_id=0, det_size=(det_size, det_size))
                _engine_instance = app
    return _engine_instance


def decode_image(image_bytes: bytes) -> np.ndarray:
    """Decode encoded image bytes into an OpenCV BGR image."""
    image = cv2.imdecode(
        np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR
    )
    if image is None or image.size == 0:
        raise ValueError("Invalid or unreadable image bytes")
    return image


def detect_faces(
    image: np.ndarray, engine: Optional[FaceAnalysis] = None
) -> List[Any]:
    """Detect faces using the provided engine or the shared singleton."""
    active_engine = engine if engine is not None else get_face_engine()
    return list(active_engine.get(image))


def extract_embedding(face: Any) -> np.ndarray:
    """Return a contiguous, unit-length float32 embedding for a face."""
    if (
        hasattr(face, "normed_embedding")
        and face.normed_embedding is not None
    ):
        vec = face.normed_embedding
    elif hasattr(face, "embedding") and face.embedding is not None:
        embedding = np.asarray(face.embedding)
        norm = np.linalg.norm(embedding)
        vec = embedding / (norm + 1e-10)
    else:
        raise ValueError("Face object contains no embedding feature")
    return np.ascontiguousarray(vec, dtype=np.float32)


def embedding_to_bytes(vec: np.ndarray) -> bytes:
    """Serialize a 512-dimensional embedding as a raw float32 BLOB."""
    vector = np.asarray(vec)
    if vector.size != 512:
        raise ValueError("Embedding must contain exactly 512 values")
    return vector.astype(np.float32).tobytes()


def bytes_to_embedding(blob: bytes) -> np.ndarray:
    """Restore a 512-dimensional float32 embedding from its raw BLOB."""
    if len(blob) != 512 * np.dtype(np.float32).itemsize:
        raise ValueError("Embedding BLOB must be exactly 2048 bytes")
    return np.frombuffer(blob, dtype=np.float32)


def compute_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
    """Calculate cosine similarity for unit-length embedding vectors."""
    return float(np.dot(emb1, emb2))


def estimate_yaw(face: Any) -> float:
    """Estimate yaw in degrees, preferring InsightFace's 3D pose output."""
    pose = getattr(face, "pose", None)
    if pose is not None and len(pose) >= 2:
        return float(pose[1])

    landmarks = getattr(face, "kps", None)
    if landmarks is None:
        return 0.0
    points = np.asarray(landmarks)
    if points.ndim != 2 or points.shape[0] < 3 or points.shape[1] < 2:
        return 0.0

    left_eye_x = float(points[0, 0])
    right_eye_x = float(points[1, 0])
    nose_x = float(points[2, 0])
    left_distance = abs(nose_x - left_eye_x)
    right_distance = abs(right_eye_x - nose_x)
    distance_sum = left_distance + right_distance
    if distance_sum == 0.0:
        return 0.0

    # Convert the eye-to-nose distance imbalance to an approximate signed angle.
    imbalance = (right_distance - left_distance) / distance_sum
    return float(np.degrees(np.arcsin(np.clip(imbalance, -1.0, 1.0))))


def classify_pose_angle(yaw: float) -> str:
    """Classify a yaw angle as front, left, or right."""
    if abs(yaw) <= 15.0:
        return "front"
    if yaw > 15.0:
        return "left"
    return "right"
