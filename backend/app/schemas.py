"""Pydantic request, response, and transfer schemas for the Attendance AI API."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# Authentication and users
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: Literal["admin", "lecturer"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: str
    created_at: datetime


# Students and biometrics
class StudentCreate(BaseModel):
    student_code: str
    full_name: str
    level: str
    group_name: str
    consent: bool = True


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_code: str
    full_name: str
    level: str
    group_name: str
    consent_at: datetime
    enrolled_faces_count: int = 0


class FaceCheckResult(BaseModel):
    face_detected: bool
    face_count: int
    size_ok: bool
    blur_ok: bool
    brightness_ok: bool
    angle: Literal["front", "left", "right", "unknown"]
    is_valid: bool
    message: str


class FaceEnrollmentResult(BaseModel):
    student_id: int
    enrolled_count: int
    angles: List[str]
    message: str


# Courses and course rosters
class CourseCreate(BaseModel):
    code: str
    name: str
    lecturer_id: int


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    lecturer_id: int
    lecturer_name: Optional[str] = None
    student_count: int = 0


class CourseRosterUpdate(BaseModel):
    student_ids: List[int]


# Attendance sessions and recognition
class SessionCreate(BaseModel):
    course_id: int


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    started_at: datetime
    status: str


class RecognizedStudent(BaseModel):
    student_id: int
    student_code: str
    full_name: str
    confidence: float
    status: Literal["present", "absent", "excused"] = "present"


class RecognitionResult(BaseModel):
    session_id: int
    photos_processed: int
    total_detected_faces: int
    recognized_students: List[RecognizedStudent]
    absent_students: List[StudentOut]
    unknown_faces_count: int


class AttendanceItem(BaseModel):
    student_id: int
    status: Literal["present", "absent", "excused"]
    source: Literal["auto", "manual"] = "auto"
    confidence: Optional[float] = None


class AttendanceCommit(BaseModel):
    records: List[AttendanceItem]


class AttendanceRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    student_id: int
    status: str
    source: str
    confidence: Optional[float] = None
    student_code: Optional[str] = None
    student_name: Optional[str] = None


# Reports and system health
class StudentAttendanceStat(BaseModel):
    student_id: int
    student_code: str
    full_name: str
    total_sessions: int
    attended_sessions: int
    attendance_percentage: float


class CourseReport(BaseModel):
    course_id: int
    course_code: str
    course_name: str
    total_sessions: int
    students: List[StudentAttendanceStat]


class HealthCheck(BaseModel):
    status: str = "healthy"
    model_loaded: bool
    cached_vectors_count: int
    database: str
