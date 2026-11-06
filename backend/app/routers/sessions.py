"""Course session, face recognition, and attendance commit endpoints."""

from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

try:
    from ..auth import require_role
    from ..config import settings
    from ..db import get_db
    from ..models import AttendanceRecord, Course, CourseStudent, FaceEmbedding, Session, Student, User
    from ..schemas import AttendanceCommit, AttendanceRecordOut, RecognitionResult, RecognizedStudent, SessionOut, StudentOut
    from ..services.face_engine import classify_pose_angle, decode_image, detect_faces, estimate_yaw, extract_embedding
    from ..services.matcher import match_faces_against_roster
except (ImportError, ValueError):
    try:
        from backend.app.auth import require_role
        from backend.app.config import settings
        from backend.app.db import get_db
        from backend.app.models import AttendanceRecord, Course, CourseStudent, FaceEmbedding, Session, Student, User
        from backend.app.schemas import AttendanceCommit, AttendanceRecordOut, RecognitionResult, RecognizedStudent, SessionOut, StudentOut
        from backend.app.services.face_engine import classify_pose_angle, decode_image, detect_faces, estimate_yaw, extract_embedding
        from backend.app.services.matcher import match_faces_against_roster
    except ModuleNotFoundError:
        from app.auth import require_role
        from app.config import settings
        from app.db import get_db
        from app.models import AttendanceRecord, Course, CourseStudent, FaceEmbedding, Session, Student, User
        from app.schemas import AttendanceCommit, AttendanceRecordOut, RecognitionResult, RecognizedStudent, SessionOut, StudentOut
        from app.services.face_engine import classify_pose_angle, decode_image, detect_faces, estimate_yaw, extract_embedding
        from app.services.matcher import match_faces_against_roster


router = APIRouter(prefix="/api", tags=["sessions"])


def _check_course_access(course: Course, user: User) -> None:
    if user.role == "lecturer" and course.lecturer_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this course.")


def _get_session(session_id: int, db: DbSession) -> Session:
    session = db.query(Session).filter(Session.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session with id {session_id} not found.")
    return session


def _check_session_access(session: Session, user: User) -> None:
    _check_course_access(session.course, user)


@router.post("/courses/{course_id}/sessions", response_model=SessionOut)
def open_session(course_id: int, db: DbSession = Depends(get_db), current_user: User = Depends(require_role("lecturer", "admin"))) -> SessionOut:
    course = db.query(Course).filter(Course.id == course_id).first()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Course with id {course_id} not found.")
    _check_course_access(course, current_user)
    session = Session(course_id=course_id, status="open")
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionOut.model_validate(session)


@router.get("/courses/{course_id}/sessions", response_model=List[SessionOut])
def list_sessions(course_id: int, db: DbSession = Depends(get_db), current_user: User = Depends(require_role("lecturer", "admin"))) -> List[SessionOut]:
    course = db.query(Course).filter(Course.id == course_id).first()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Course with id {course_id} not found.")
    _check_course_access(course, current_user)
    return [SessionOut.model_validate(s) for s in db.query(Session).filter(Session.course_id == course_id).order_by(Session.started_at.desc()).all()]


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: int, db: DbSession = Depends(get_db), current_user: User = Depends(require_role("lecturer", "admin"))) -> SessionOut:
    session = _get_session(session_id, db)
    _check_session_access(session, current_user)
    return SessionOut.model_validate(session)


@router.post("/sessions/{session_id}/recognize", response_model=RecognitionResult)
def recognize(session_id: int, photos: List[UploadFile] = File(default=[]), db: DbSession = Depends(get_db), current_user: User = Depends(require_role("lecturer", "admin"))) -> RecognitionResult:
    session = _get_session(session_id, db)
    if session.status != "open":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is closed")
    _check_session_access(session, current_user)
    if not 1 <= len(photos) <= 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload between 1 and 5 photos.")

    query_faces = []
    for photo in photos:
        content = photo.file.read()
        if len(content) > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Photo exceeds the maximum allowed upload size.")
        try:
            image = decode_image(content)
            faces = detect_faces(image)
            for face in faces:
                query_faces.append({"embedding": extract_embedding(face), "angle": classify_pose_angle(estimate_yaw(face))})
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid photo or face data: {exc}") from exc

    roster_student_ids = [sid for (sid,) in db.query(CourseStudent.student_id).filter(CourseStudent.course_id == session.course_id).all()]
    try:
        match_result = match_faces_against_roster(query_faces, roster_student_ids, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unable to process detected faces: {exc}") from exc
    recognized = [RecognizedStudent(student_id=r["student_id"], student_code=r["student_code"], full_name=r["full_name"], confidence=r["confidence"], status="present") for r in match_result["recognized"]]
    matched_ids = set(match_result["matched_student_ids"])
    absent_rows = (db.query(Student, func.count(FaceEmbedding.id).label("face_count"))
        .join(CourseStudent, CourseStudent.student_id == Student.id)
        .outerjoin(FaceEmbedding, FaceEmbedding.student_id == Student.id)
        .filter(CourseStudent.course_id == session.course_id, ~Student.id.in_(matched_ids) if matched_ids else True)
        .group_by(Student.id).order_by(Student.student_code.asc()).all())
    absent = [StudentOut(id=s.id, student_code=s.student_code, full_name=s.full_name, level=s.level, group_name=s.group_name, consent_at=s.consent_at, enrolled_faces_count=count) for s, count in absent_rows]
    return RecognitionResult(session_id=session_id, photos_processed=len(photos), total_detected_faces=len(query_faces), recognized_students=recognized, absent_students=absent, unknown_faces_count=match_result["unknown_count"])


@router.put("/sessions/{session_id}/attendance", response_model=List[AttendanceRecordOut])
def commit_attendance(session_id: int, payload: AttendanceCommit, db: DbSession = Depends(get_db), current_user: User = Depends(require_role("lecturer", "admin"))) -> List[AttendanceRecordOut]:
    session = _get_session(session_id, db)
    if session.status != "open":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is closed")
    _check_session_access(session, current_user)
    roster_ids = {sid for (sid,) in db.query(CourseStudent.student_id).filter(CourseStudent.course_id == session.course_id).all()}
    submitted_ids = [item.student_id for item in payload.records]
    if len(submitted_ids) != len(set(submitted_ids)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attendance contains duplicate student records.")
    if any(student_id not in roster_ids for student_id in submitted_ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attendance contains a student not enrolled in this course.")

    db.query(AttendanceRecord).filter(AttendanceRecord.session_id == session_id).delete(synchronize_session=False)
    records = [AttendanceRecord(session_id=session_id, student_id=item.student_id, status=item.status, source=item.source, confidence=item.confidence) for item in payload.records]
    db.add_all(records)
    session.status = "closed"
    db.commit()
    rows = (db.query(AttendanceRecord, Student.student_code, Student.full_name)
        .join(Student, Student.id == AttendanceRecord.student_id)
        .filter(AttendanceRecord.session_id == session_id).order_by(Student.student_code.asc()).all())
    return [AttendanceRecordOut(id=record.id, session_id=record.session_id, student_id=record.student_id, status=record.status, source=record.source, confidence=record.confidence, student_code=code, student_name=name) for record, code, name in rows]
