"""Course attendance summaries and CSV exports."""

import csv
import io
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

try:
    from ..auth import require_role
    from ..db import get_db
    from ..models import AttendanceRecord, Course, CourseStudent, Session, Student, User
    from ..schemas import CourseReport, StudentAttendanceStat
except (ImportError, ValueError):
    try:
        from backend.app.auth import require_role
        from backend.app.db import get_db
        from backend.app.models import AttendanceRecord, Course, CourseStudent, Session, Student, User
        from backend.app.schemas import CourseReport, StudentAttendanceStat
    except ModuleNotFoundError:
        from app.auth import require_role
        from app.db import get_db
        from app.models import AttendanceRecord, Course, CourseStudent, Session, Student, User
        from app.schemas import CourseReport, StudentAttendanceStat


router = APIRouter(prefix="/api", tags=["reports"])


def _build_report(course_id: int, db: DBSession, current_user: User) -> CourseReport:
    course = db.query(Course).filter(Course.id == course_id).first()
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course with id {course_id} not found.",
        )
    if current_user.role == "lecturer" and course.lecturer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this course's report.",
        )

    total_sessions = (
        db.query(func.count(Session.id))
        .filter(Session.course_id == course_id, Session.status == "closed")
        .scalar()
        or 0
    )
    students = (
        db.query(Student)
        .join(CourseStudent, CourseStudent.student_id == Student.id)
        .filter(CourseStudent.course_id == course_id)
        .order_by(Student.student_code.asc())
        .all()
    )
    attended_counts = dict(
        db.query(AttendanceRecord.student_id, func.count(func.distinct(AttendanceRecord.session_id)))
        .join(Session, Session.id == AttendanceRecord.session_id)
        .join(CourseStudent, CourseStudent.student_id == AttendanceRecord.student_id)
        .filter(
            CourseStudent.course_id == course_id,
            Session.course_id == course_id,
            Session.status == "closed",
            AttendanceRecord.status == "present",
        )
        .group_by(AttendanceRecord.student_id)
        .all()
    )

    student_stats: List[StudentAttendanceStat] = []
    for student in students:
        attended = attended_counts.get(student.id, 0)
        percentage = round((attended / total_sessions) * 100.0, 2) if total_sessions else 0.0
        student_stats.append(
            StudentAttendanceStat(
                student_id=student.id,
                student_code=student.student_code,
                full_name=student.full_name,
                total_sessions=total_sessions,
                attended_sessions=attended,
                attendance_percentage=percentage,
            )
        )
    return CourseReport(
        course_id=course.id,
        course_code=course.code,
        course_name=course.name,
        total_sessions=total_sessions,
        students=student_stats,
    )


@router.get("/courses/{course_id}/report", response_model=CourseReport)
def get_course_report(
    course_id: int,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(require_role("lecturer", "admin")),
) -> CourseReport:
    """Return attendance statistics for every student on a course roster."""
    return _build_report(course_id, db, current_user)


@router.get("/courses/{course_id}/report/csv")
def get_course_report_csv(
    course_id: int,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(require_role("lecturer", "admin")),
) -> Response:
    """Download the course attendance report as an Excel-friendly UTF-8 CSV."""
    report = _build_report(course_id, db, current_user)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Student Code", "Full Name", "Total Sessions", "Attended Sessions", "Attendance Rate (%)"])
    for student in report.students:
        writer.writerow([
            student.student_code,
            student.full_name,
            student.total_sessions,
            student.attended_sessions,
            student.attendance_percentage,
        ])
    content = "\ufeff" + output.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="attendance_report_{report.course_code}.csv"'},
    )
