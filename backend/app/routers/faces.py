"""Face quality preview, enrollment, and biometric revocation endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

try:
    from ..auth import require_role
    from ..config import settings
    from ..db import get_db
    from ..models import Student, FaceEmbedding, User
    from ..schemas import FaceCheckResult, FaceEnrollmentResult
    from ..services.face_engine import (
        decode_image,
        detect_faces,
        extract_embedding,
        embedding_to_bytes,
    )
    from ..services.quality import check_image_quality
    from ..services.matcher import vector_cache
except (ImportError, ValueError):
    try:
        from backend.app.auth import require_role
        from backend.app.config import settings
        from backend.app.db import get_db
        from backend.app.models import Student, FaceEmbedding, User
        from backend.app.schemas import FaceCheckResult, FaceEnrollmentResult
        from backend.app.services.face_engine import (
            decode_image,
            detect_faces,
            extract_embedding,
            embedding_to_bytes,
        )
        from backend.app.services.quality import check_image_quality
        from backend.app.services.matcher import vector_cache
    except ModuleNotFoundError:
        from app.auth import require_role
        from app.config import settings
        from app.db import get_db
        from app.models import Student, FaceEmbedding, User
        from app.schemas import FaceCheckResult, FaceEnrollmentResult
        from app.services.face_engine import (
            decode_image,
            detect_faces,
            extract_embedding,
            embedding_to_bytes,
        )
        from app.services.quality import check_image_quality
        from app.services.matcher import vector_cache


router = APIRouter(prefix="/api", tags=["faces"])


def _read_limited(file: UploadFile) -> bytes:
    """Read an upload once and reject it when it exceeds configured limit."""
    contents = file.file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds the {settings.MAX_UPLOAD_MB} MB upload limit.",
        )
    return contents


@router.post("/faces/check", response_model=FaceCheckResult)
def check_face(
    file: UploadFile = File(...),
    target_angle: Optional[str] = Form(None),
    _current_user: User = Depends(require_role("admin")),
) -> FaceCheckResult:
    contents = _read_limited(file)
    try:
        image = decode_image(contents)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file or format.",
        )
    return check_image_quality(image, target_angle=target_angle)


@router.post("/students/{id}/faces", response_model=FaceEnrollmentResult)
def enroll_faces(
    id: int,
    front_photo: UploadFile = File(...),
    left_photo: UploadFile = File(...),
    right_photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
) -> FaceEnrollmentResult:
    student = db.query(Student).filter(Student.id == id).first()
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with id {id} not found.",
        )

    extracted_embeddings = []
    for angle, photo in (
        ("front", front_photo),
        ("left", left_photo),
        ("right", right_photo),
    ):
        contents = _read_limited(photo)
        try:
            image = decode_image(contents)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid image file or format for {angle} photo.",
            )

        result = check_image_quality(image, target_angle=angle)
        if not result.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Enrollment rejected for {angle} photo: {result.message}",
            )

        faces = detect_faces(image)
        if not faces:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Enrollment rejected for {angle} photo: No face detected in image",
            )
        try:
            embedding = extract_embedding(faces[0])
            vector_blob = embedding_to_bytes(embedding)
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Enrollment rejected for {angle} photo: Invalid face embedding.",
            ) from exc
        extracted_embeddings.append((angle, vector_blob))

    try:
        db.query(FaceEmbedding).filter(FaceEmbedding.student_id == id).delete()
        for angle, vector_blob in extracted_embeddings:
            db.add(FaceEmbedding(student_id=id, vector=vector_blob, angle=angle))
        db.commit()
    except Exception:
        db.rollback()
        raise

    vector_cache.invalidate()
    return FaceEnrollmentResult(
        student_id=id,
        enrolled_count=3,
        angles=["front", "left", "right"],
        message=f"Successfully enrolled 3 face poses for student '{student.student_code}'.",
    )


@router.delete("/students/{id}/faces")
def revoke_faces(
    id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
) -> dict:
    student = db.query(Student).filter(Student.id == id).first()
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with id {id} not found.",
        )

    try:
        deleted_count = (
            db.query(FaceEmbedding)
            .filter(FaceEmbedding.student_id == id)
            .delete()
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    vector_cache.invalidate()
    return {
        "message": f"Revoked {deleted_count} face embeddings for student '{student.student_code}'.",
        "student_id": id,
        "deleted_count": deleted_count,
    }
