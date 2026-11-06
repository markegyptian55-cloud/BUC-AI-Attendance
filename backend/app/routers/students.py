"""Student directory and profile management endpoints."""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

try:
    from ..auth import require_role
    from ..db import get_db
    from ..models import Student, FaceEmbedding, User
    from ..schemas import StudentCreate, StudentOut
    from ..services.matcher import vector_cache
except (ImportError, ValueError):
    try:
        from backend.app.auth import require_role
        from backend.app.db import get_db
        from backend.app.models import Student, FaceEmbedding, User
        from backend.app.schemas import StudentCreate, StudentOut
        from backend.app.services.matcher import vector_cache
    except ModuleNotFoundError:
        from app.auth import require_role
        from app.db import get_db
        from app.models import Student, FaceEmbedding, User
        from app.schemas import StudentCreate, StudentOut
        from app.services.matcher import vector_cache


router = APIRouter(prefix="/api", tags=["students"])


@router.get("/students", response_model=List[StudentOut])
def list_students(
    search: Optional[str] = Query(None, description="Search by student code or full name"),
    level: Optional[str] = Query(None, description="Filter by level"),
    group_name: Optional[str] = Query(None, description="Filter by group name"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin", "lecturer")),
) -> List[StudentOut]:
    """List students and their number of enrolled face embeddings."""
    query = (
        db.query(Student, func.count(FaceEmbedding.id).label("enrolled_faces_count"))
        .outerjoin(FaceEmbedding, FaceEmbedding.student_id == Student.id)
        .group_by(Student.id)
    )
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(Student.student_code.ilike(pattern), Student.full_name.ilike(pattern))
        )
    if level:
        query = query.filter(Student.level == level)
    if group_name:
        query = query.filter(Student.group_name == group_name)

    rows = query.order_by(Student.student_code.asc()).all()
    return [
        StudentOut(
            id=student.id,
            student_code=student.student_code,
            full_name=student.full_name,
            level=student.level,
            group_name=student.group_name,
            consent_at=student.consent_at,
            enrolled_faces_count=count,
        )
        for student, count in rows
    ]


@router.post("/students", response_model=StudentOut)
def create_student(
    student_in: StudentCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
) -> StudentOut:
    """Register a student after confirming biometric consent."""
    if not student_in.consent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Biometric consent is legally required to register a student.",
        )

    existing = (
        db.query(Student)
        .filter(Student.student_code == student_in.student_code)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Student code '{student_in.student_code}' is already registered.",
        )

    student = Student(
        student_code=student_in.student_code,
        full_name=student_in.full_name,
        level=student_in.level,
        group_name=student_in.group_name,
        consent_at=datetime.now(timezone.utc),
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return StudentOut(
        id=student.id,
        student_code=student.student_code,
        full_name=student.full_name,
        level=student.level,
        group_name=student.group_name,
        consent_at=student.consent_at,
        enrolled_faces_count=0,
    )


@router.delete("/students/{id}")
def delete_student(
    id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
) -> dict:
    """Delete a student and invalidate cached face vectors."""
    student = db.query(Student).filter(Student.id == id).first()
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with id {id} not found.",
        )

    student_code = student.student_code
    db.delete(student)
    db.commit()
    vector_cache.invalidate()
    return {"message": f"Student '{student_code}' deleted successfully", "id": id}
