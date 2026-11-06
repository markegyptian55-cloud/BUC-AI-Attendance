"""Academic course and roster management endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

try:
    from ..auth import require_role
    from ..db import get_db
    from ..models import Course, CourseStudent, Student, User, FaceEmbedding
    from ..schemas import CourseCreate, CourseOut, CourseRosterUpdate, StudentOut
except (ImportError, ValueError):
    try:
        from backend.app.auth import require_role
        from backend.app.db import get_db
        from backend.app.models import Course, CourseStudent, Student, User, FaceEmbedding
        from backend.app.schemas import CourseCreate, CourseOut, CourseRosterUpdate, StudentOut
    except ModuleNotFoundError:
        from app.auth import require_role
        from app.db import get_db
        from app.models import Course, CourseStudent, Student, User, FaceEmbedding
        from app.schemas import CourseCreate, CourseOut, CourseRosterUpdate, StudentOut


router = APIRouter(prefix="/api", tags=["courses"])


@router.get("/courses", response_model=List[CourseOut])
def list_courses(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "lecturer")),
) -> List[CourseOut]:
    """List visible courses with lecturer names and roster sizes."""
    query = (
        db.query(Course, User.full_name.label("lecturer_name"),
                 func.count(CourseStudent.student_id).label("student_count"))
        .join(User, User.id == Course.lecturer_id)
        .outerjoin(CourseStudent, CourseStudent.course_id == Course.id)
        .group_by(Course.id, User.full_name)
    )
    if current_user.role == "lecturer":
        query = query.filter(Course.lecturer_id == current_user.id)
    rows = query.order_by(Course.code.asc()).all()
    return [
        CourseOut(
            id=course.id, code=course.code, name=course.name,
            lecturer_id=course.lecturer_id, lecturer_name=lecturer_name,
            student_count=count,
        )
        for course, lecturer_name, count in rows
    ]


@router.post("/courses", response_model=CourseOut)
def create_course(
    course_in: CourseCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
) -> CourseOut:
    """Create a course assigned to an existing lecturer or admin."""
    if db.query(Course).filter(Course.code == course_in.code).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Course code '{course_in.code}' already exists.",
        )
    lecturer = db.query(User).filter(User.id == course_in.lecturer_id).first()
    if lecturer is None or lecturer.role not in ("lecturer", "admin"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid lecturer ID")

    course = Course(code=course_in.code, name=course_in.name, lecturer_id=course_in.lecturer_id)
    db.add(course)
    db.commit()
    db.refresh(course)
    return CourseOut(
        id=course.id, code=course.code, name=course.name,
        lecturer_id=course.lecturer_id, lecturer_name=lecturer.full_name, student_count=0,
    )


@router.put("/courses/{id}/students")
def replace_course_roster(
    id: int,
    roster_in: CourseRosterUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
) -> dict:
    """Atomically replace a course's enrolled student IDs."""
    course = db.query(Course).filter(Course.id == id).first()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Course with id {id} not found.")

    student_ids = set(roster_in.student_ids)
    existing_ids = {
        student_id for (student_id,) in db.query(Student.id)
        .filter(Student.id.in_(student_ids)).all()
    } if student_ids else set()
    invalid_ids = sorted(student_ids - existing_ids)
    if invalid_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid student IDs: {invalid_ids}",
        )

    db.query(CourseStudent).filter(CourseStudent.course_id == id).delete(synchronize_session=False)
    db.add_all(CourseStudent(course_id=id, student_id=sid) for sid in student_ids)
    db.commit()
    return {
        "message": f"Updated roster for course '{course.code}'.",
        "course_id": id,
        "student_count": len(student_ids),
    }


@router.get("/courses/{id}/students", response_model=List[StudentOut])
def list_course_students(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "lecturer")),
) -> List[StudentOut]:
    """List roster students and their enrolled face counts."""
    course = db.query(Course).filter(Course.id == id).first()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Course with id {id} not found.")
    if current_user.role == "lecturer" and course.lecturer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this course's roster.",
        )

    rows = (
        db.query(Student, func.count(FaceEmbedding.id).label("enrolled_faces_count"))
        .join(CourseStudent, Student.id == CourseStudent.student_id)
        .outerjoin(FaceEmbedding, FaceEmbedding.student_id == Student.id)
        .filter(CourseStudent.course_id == id)
        .group_by(Student.id)
        .order_by(Student.student_code.asc())
        .all()
    )
    return [
        StudentOut(
            id=student.id, student_code=student.student_code, full_name=student.full_name,
            level=student.level, group_name=student.group_name, consent_at=student.consent_at,
            enrolled_faces_count=count,
        )
        for student, count in rows
    ]
