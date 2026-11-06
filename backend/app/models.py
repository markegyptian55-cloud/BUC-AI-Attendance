"""SQLAlchemy models for attendance, course rosters, and face embeddings."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from .db import Base
except (ImportError, ValueError):
    try:
        from backend.app.db import Base
    except ModuleNotFoundError:
        from app.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin', 'lecturer')", name="chk_user_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    courses: Mapped[List["Course"]] = relationship("Course", back_populates="lecturer")


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=False)
    group_name: Mapped[str] = mapped_column(String(50), nullable=False)
    consent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    embeddings: Mapped[List["FaceEmbedding"]] = relationship(
        "FaceEmbedding", back_populates="student", cascade="all, delete-orphan"
    )
    course_associations: Mapped[List["CourseStudent"]] = relationship(
        "CourseStudent", back_populates="student", cascade="all, delete-orphan"
    )
    attendance_records: Mapped[List["AttendanceRecord"]] = relationship(
        "AttendanceRecord", back_populates="student", cascade="all, delete-orphan"
    )


class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"
    __table_args__ = (CheckConstraint("angle IN ('front', 'left', 'right')", name="chk_face_angle"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    angle: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    student: Mapped["Student"] = relationship("Student", back_populates="embeddings")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    lecturer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    lecturer: Mapped["User"] = relationship("User", back_populates="courses")
    student_associations: Mapped[List["CourseStudent"]] = relationship(
        "CourseStudent", back_populates="course", cascade="all, delete-orphan"
    )
    sessions: Mapped[List["Session"]] = relationship(
        "Session", back_populates="course", cascade="all, delete-orphan"
    )


class CourseStudent(Base):
    __tablename__ = "course_students"

    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), primary_key=True
    )

    course: Mapped["Course"] = relationship("Course", back_populates="student_associations")
    student: Mapped["Student"] = relationship("Student", back_populates="course_associations")


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (CheckConstraint("status IN ('open', 'closed')", name="chk_session_status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)

    course: Mapped["Course"] = relationship("Course", back_populates="sessions")
    records: Mapped[List["AttendanceRecord"]] = relationship(
        "AttendanceRecord", back_populates="session", cascade="all, delete-orphan"
    )


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_session_student"),
        CheckConstraint("status IN ('present', 'absent', 'excused')", name="chk_record_status"),
        CheckConstraint("source IN ('auto', 'manual')", name="chk_record_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="auto", nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    session: Mapped["Session"] = relationship("Session", back_populates="records")
    student: Mapped["Student"] = relationship("Student", back_populates="attendance_records")
