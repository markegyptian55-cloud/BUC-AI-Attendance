"""Strict image and pose quality checks for face enrollment and recognition."""

from typing import Any, List, Optional, Tuple

import cv2
import numpy as np

try:
    from ..schemas import FaceCheckResult
    from .face_engine import estimate_yaw, detect_faces
except (ImportError, ValueError):
    try:
        from backend.app.schemas import FaceCheckResult
        from backend.app.services.face_engine import estimate_yaw, detect_faces
    except ModuleNotFoundError:
        from app.schemas import FaceCheckResult
        from app.services.face_engine import estimate_yaw, detect_faces


MIN_FACE_DIMENSION = 90
MIN_BLUR_SCORE = 50.0
MIN_BRIGHTNESS = 40.0
MAX_BRIGHTNESS = 215.0


def _to_grayscale(image_or_crop: np.ndarray) -> np.ndarray:
    """Convert a BGR or single-channel image to grayscale."""
    if image_or_crop.ndim == 3 and image_or_crop.shape[2] == 3:
        return cv2.cvtColor(image_or_crop, cv2.COLOR_BGR2GRAY)
    if image_or_crop.ndim == 3 and image_or_crop.shape[2] == 1:
        return image_or_crop[:, :, 0]
    return image_or_crop


def compute_blur_score(image_or_crop: np.ndarray) -> float:
    """Return Laplacian variance; larger values indicate a sharper image."""
    gray = _to_grayscale(image_or_crop)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def compute_brightness_score(image_or_crop: np.ndarray) -> float:
    """Return mean grayscale pixel intensity."""
    gray = _to_grayscale(image_or_crop)
    return float(np.mean(gray))


def classify_yaw_angle(yaw: float) -> str:
    """Map signed yaw in degrees to a capture pose label."""
    if abs(yaw) <= 12.0:
        return "front"
    if yaw >= 20.0:
        return "left"
    if yaw <= -20.0:
        return "right"
    return "unknown"


def _invalid_face_result(message: str) -> FaceCheckResult:
    return FaceCheckResult(
        face_detected=True,
        face_count=1,
        size_ok=False,
        blur_ok=False,
        brightness_ok=False,
        angle="unknown",
        is_valid=False,
        message=message,
    )


def assess_face_quality(
    image: np.ndarray,
    face: Any,
    target_angle: Optional[str] = None,
) -> FaceCheckResult:
    """Evaluate one detected face against size, image, and pose thresholds."""
    height, width = image.shape[:2]
    bbox = np.asarray(face.bbox).reshape(-1)
    if bbox.size < 4:
        return _invalid_face_result("Face bounding box is invalid")

    x1 = int(np.clip(bbox[0], 0, width))
    y1 = int(np.clip(bbox[1], 0, height))
    x2 = int(np.clip(bbox[2], 0, width))
    y2 = int(np.clip(bbox[3], 0, height))
    face_width = max(0, x2 - x1)
    face_height = max(0, y2 - y1)
    size_ok = face_width >= MIN_FACE_DIMENSION and face_height >= MIN_FACE_DIMENSION

    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return _invalid_face_result("Face crop is empty")

    blur = compute_blur_score(crop)
    blur_ok = blur >= MIN_BLUR_SCORE
    brightness = compute_brightness_score(crop)
    brightness_ok = MIN_BRIGHTNESS <= brightness <= MAX_BRIGHTNESS
    yaw = float(estimate_yaw(face))
    detected_angle = classify_yaw_angle(yaw)
    angle_ok = (
        detected_angle == target_angle
        if target_angle is not None
        else detected_angle in ("front", "left", "right")
    )
    is_valid = size_ok and blur_ok and brightness_ok and angle_ok

    failures: List[str] = []
    if not size_ok:
        failures.append(
            f"Face too small ({face_width}x{face_height} px < {MIN_FACE_DIMENSION}px)"
        )
    if not blur_ok:
        failures.append(f"Image too blurry (score {blur:.1f} < {MIN_BLUR_SCORE:.1f})")
    if brightness < MIN_BRIGHTNESS:
        failures.append(
            f"Image too dark (brightness {brightness:.1f} < {MIN_BRIGHTNESS:.1f})"
        )
    elif brightness > MAX_BRIGHTNESS:
        failures.append(
            f"Image too bright (brightness {brightness:.1f} > {MAX_BRIGHTNESS:.1f})"
        )
    if not angle_ok:
        if target_angle is not None:
            failures.append(
                f"Expected {target_angle} face but detected {detected_angle} pose "
                f"(yaw {yaw:.1f}\N{DEGREE SIGN})"
            )
        else:
            failures.append(f"Head pose is not a supported capture angle (yaw {yaw:.1f}\N{DEGREE SIGN})")

    return FaceCheckResult(
        face_detected=True,
        face_count=1,
        size_ok=size_ok,
        blur_ok=blur_ok,
        brightness_ok=brightness_ok,
        angle=detected_angle,
        is_valid=is_valid,
        message="Face quality check passed" if is_valid else "; ".join(failures),
    )


def check_image_quality(
    image: np.ndarray,
    engine: Optional[Any] = None,
    target_angle: Optional[str] = None,
) -> FaceCheckResult:
    """Detect faces and enforce the single-face quality gate."""
    faces = detect_faces(image, engine)
    if len(faces) == 0:
        return FaceCheckResult(
            face_detected=False,
            face_count=0,
            size_ok=False,
            blur_ok=False,
            brightness_ok=False,
            angle="unknown",
            is_valid=False,
            message="No face detected in image",
        )
    if len(faces) > 1:
        return FaceCheckResult(
            face_detected=True,
            face_count=len(faces),
            size_ok=False,
            blur_ok=False,
            brightness_ok=False,
            angle="unknown",
            is_valid=False,
            message=(
                f"Multiple faces detected ({len(faces)}). "
                "Please ensure only one person is in frame."
            ),
        )
    return assess_face_quality(image, faces[0], target_angle)

