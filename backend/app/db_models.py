"""
SQLAlchemy Relational Database Models for ChronoScheduler.
Defines SQL tables for Departments, Sections, Academic Years, Years, Semesters,
Users, Subjects, Classrooms, TimeSlots, Faculty Allocations, and Generated Timetables.
Compatible with SQLite, PostgreSQL, and MySQL.
"""

from datetime import datetime, date, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import relationship
from app.database import Base

class DepartmentDB(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False)

class SectionDB(Base):
    __tablename__ = "sections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(20), unique=True, nullable=False)

class AcademicYearDB(Base):
    __tablename__ = "academic_years"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    is_current = Column(Boolean, default=True)

class YearDB(Base):
    __tablename__ = "years"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    academic_level = Column(Integer, nullable=False)

class SemesterDB(Base):
    __tablename__ = "semesters"

    id = Column(Integer, primary_key=True, index=True)
    year_id = Column(Integer, ForeignKey("years.id"), nullable=False)
    name = Column(String(50), nullable=False)
    term_number = Column(Integer, nullable=False)

class UserDB(Base):
    __tablename__ = "users"

    id = Column(String(50), primary_key=True, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    role = Column(String(20), nullable=False)  # "ADMIN" or "FACULTY"
    department = Column(String(150), nullable=False)
    department_code = Column(String(20), default="CSE")

class SubjectDB(Base):
    __tablename__ = "subjects"

    id = Column(String(50), primary_key=True, index=True)
    code = Column(String(30), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    department_code = Column(String(20), nullable=False)
    semester_id = Column(Integer, ForeignKey("semesters.id"), nullable=False)
    weekly_hours = Column(Integer, default=3)
    is_lab = Column(Boolean, default=False)

class ClassroomDB(Base):
    __tablename__ = "classrooms"

    id = Column(Integer, primary_key=True, index=True)
    room_number = Column(String(80), nullable=False)
    building = Column(String(100), default="Main Block")
    capacity = Column(Integer, default=60)

class TimeSlotDB(Base):
    __tablename__ = "time_slots"

    id = Column(Integer, primary_key=True, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday ... 4=Friday
    day_name = Column(String(20), nullable=False)
    slot_index = Column(Integer, nullable=False)  # 1 to 6 (0 for lunch break)
    start_time = Column(String(10), nullable=False)  # "09:20"
    end_time = Column(String(10), nullable=False)    # "10:20"
    is_break = Column(Boolean, default=False)

class FacultyAllocationDB(Base):
    __tablename__ = "faculty_allocations"

    id = Column(String(50), primary_key=True, index=True)
    faculty_id = Column(String(50), ForeignKey("users.id"), unique=True, nullable=False, index=True)  # Strict 1:1 constraint
    subject_id = Column(String(50), ForeignKey("subjects.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    department_code = Column(String(20), nullable=False)
    year_id = Column(Integer, ForeignKey("years.id"), nullable=False)
    semester_id = Column(Integer, ForeignKey("semesters.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False)
    section_name = Column(String(20), nullable=False)
    academic_year_id = Column(Integer, ForeignKey("academic_years.id"), default=1)
    allocated_by = Column(String(20), default="ADMIN")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class TimetableGenerationDB(Base):
    __tablename__ = "timetable_generations"

    id = Column(String(50), primary_key=True, index=True)
    title = Column(String(150), nullable=False)
    scope = Column(String(20), nullable=False)  # "DAY", "WEEK", "YEAR"
    status = Column(String(20), default="DRAFT") # "DRAFT", "PUBLISHED"
    academic_year_id = Column(Integer, default=1)
    target_date = Column(String(20), nullable=True)
    created_by = Column(String(100), default="Administrator")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    published_at = Column(DateTime, nullable=True)

class TimetableEntryDB(Base):
    __tablename__ = "timetable_entries"

    id = Column(String(50), primary_key=True, index=True)
    generation_id = Column(String(50), ForeignKey("timetable_generations.id"), nullable=False, index=True)
    calendar_date = Column(String(20), nullable=True)
    day_of_week = Column(Integer, nullable=False)
    day_name = Column(String(20), nullable=False)
    time_slot_id = Column(Integer, nullable=False)
    slot_index = Column(Integer, nullable=False)
    start_time = Column(String(10), nullable=False)
    end_time = Column(String(10), nullable=False)
    department_id = Column(Integer, nullable=False)
    department_code = Column(String(20), nullable=False)
    section_id = Column(Integer, nullable=False)
    section_name = Column(String(20), nullable=False)
    subject_id = Column(String(50), nullable=False)
    subject_code = Column(String(30), nullable=False)
    subject_name = Column(String(150), nullable=False)
    faculty_id = Column(String(50), nullable=False)
    faculty_name = Column(String(150), nullable=False)
    semester_id = Column(Integer, nullable=False)
    semester_name = Column(String(50), nullable=False)
    year_id = Column(Integer, nullable=False)
    year_name = Column(String(50), nullable=False)
    classroom_id = Column(Integer, nullable=False)
    classroom_name = Column(String(80), nullable=False)
    is_lab = Column(Boolean, default=False)
    is_leisure = Column(Boolean, default=False)

class SystemConfigDB(Base):
    __tablename__ = "system_config"

    key = Column(String(50), primary_key=True)
    value = Column(String(255), nullable=False)
