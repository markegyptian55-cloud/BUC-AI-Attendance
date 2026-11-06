"""Unit tests for image sharpness, exposure, pose, and face quality gates."""

import sys
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

# Support both ``pytest backend/tests`` at the repository root and
# ``pytest tests`` from the backend directory.
current_dir = Path(__file__).resolve().parent
backend_dir = current_dir.parent
project_root = backend_dir.parent
for p in [str(project_root), str(backend_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# The quality helpers are tested without loading InsightFace's model stack.
if "insightface.app" not in sys.modules:
    insightface_module = ModuleType("insightface")
    insightface_module.__path__ = []
    insightface_app_module = ModuleType("insightface.app")
    insightface_app_module.FaceAnalysis = type("FaceAnalysis", (), {})
    insightface_module.app = insightface_app_module
    sys.modules["insightface"] = insightface_module
    sys.modules["insightface.app"] = insightface_app_module

from backend.app.services import quality


def _checkerboard(size=160, low=0, high=240, block=4):
    rows, cols = np.indices((size, size))
    pattern = ((rows // block + cols // block) % 2).astype(bool)
    gray = np.where(pattern, high, low).astype(np.uint8)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def _face(yaw=0.0, bbox=(20, 20, 140, 140)):
    return SimpleNamespace(bbox=np.asarray(bbox), pose=np.asarray([0.0, yaw, 0.0]))


def test_blur_score_sharp_vs_blurred():
    sharp = _checkerboard()
    blurred = cv2.GaussianBlur(sharp, (31, 31), 0)

    assert quality.compute_blur_score(sharp) >= 50.0
    assert quality.compute_blur_score(blurred) < 50.0


def test_brightness_score_levels():
    dark = np.full((100, 100, 3), 20, dtype=np.uint8)
    normal = np.full((100, 100, 3), 120, dtype=np.uint8)
    overexposed = np.full((100, 100, 3), 240, dtype=np.uint8)

    assert quality.compute_brightness_score(dark) == pytest.approx(20.0)
    assert quality.compute_brightness_score(normal) == pytest.approx(120.0)
    assert quality.compute_brightness_score(overexposed) == pytest.approx(240.0)


def test_classify_yaw_angle_ranges():
    assert quality.classify_yaw_angle(0.0) == "front"
    assert quality.classify_yaw_angle(10.0) == "front"
    assert quality.classify_yaw_angle(15.0) == "unknown"
    assert quality.classify_yaw_angle(25.0) == "left"
    assert quality.classify_yaw_angle(-25.0) == "right"


def test_assess_face_quality_success(monkeypatch):
    monkeypatch.setattr(quality, "estimate_yaw", lambda face: 0.0)

    result = quality.assess_face_quality(_checkerboard(), _face(), target_angle="front")

    assert result.is_valid is True
    assert result.face_detected is True
    assert result.size_ok is True
    assert result.blur_ok is True
    assert result.brightness_ok is True
    assert result.angle == "front"
    assert result.message == "Face quality check passed"


def test_assess_face_quality_small_face(monkeypatch):
    monkeypatch.setattr(quality, "estimate_yaw", lambda face: 0.0)

    result = quality.assess_face_quality(
        _checkerboard(), _face(bbox=(20, 20, 100, 100)), target_angle="front"
    )

    assert result.is_valid is False
    assert result.size_ok is False
    assert "Face too small" in result.message
    assert "80x80 px" in result.message


@pytest.mark.parametrize(
    ("intensity", "message"),
    [(20, "Image too dark"), (240, "Image too bright")],
)
def test_assess_face_quality_dark_and_bright(monkeypatch, intensity, message):
    monkeypatch.setattr(quality, "estimate_yaw", lambda face: 0.0)
    image = np.full((160, 160, 3), intensity, dtype=np.uint8)

    result = quality.assess_face_quality(image, _face(), target_angle="front")

    assert result.is_valid is False
    assert result.brightness_ok is False
    assert message in result.message


def test_assess_face_quality_blurry(monkeypatch):
    monkeypatch.setattr(quality, "estimate_yaw", lambda face: 0.0)
    image = cv2.GaussianBlur(_checkerboard(), (31, 31), 0)

    result = quality.assess_face_quality(image, _face(), target_angle="front")

    assert result.is_valid is False
    assert result.blur_ok is False
    assert "Image too blurry" in result.message


def test_assess_face_quality_angle_mismatch(monkeypatch):
    monkeypatch.setattr(quality, "estimate_yaw", lambda face: 0.0)

    result = quality.assess_face_quality(_checkerboard(), _face(), target_angle="left")

    assert result.is_valid is False
    assert result.angle == "front"
    assert "Expected left face but detected front pose" in result.message


@pytest.mark.parametrize(
    ("faces", "message"),
    [([], "No face detected"), ([object(), object()], "Multiple faces detected")],
)
def test_check_image_quality_counts(monkeypatch, faces, message):
    monkeypatch.setattr(quality, "detect_faces", lambda image, engine=None: faces)

    result = quality.check_image_quality(_checkerboard(), engine=object())

    assert result.is_valid is False
    assert message in result.message
    assert result.face_count == len(faces)
