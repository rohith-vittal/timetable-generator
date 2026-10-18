from dataclasses import dataclass, field
from datetime import date, time, datetime, timezone
from enum import Enum
from typing import Optional, List, Dict
import uuid

class UserRole(str, Enum):
    ADMIN = "ADMIN"
    FACULTY = "FACULTY"

class ScheduleScope(str, Enum):
    DAY = "DAY"
    WEEK = "WEEK"
    YEAR = "YEAR"

class ScheduleStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"

@dataclass
class Department:
    id: int
    code: str # "CSE", "ECE", "EEE", "MECH"
    name: str # e.g. "Computer Science & Engineering"

@dataclass
class Section:
    id: int
    name: str # "A", "B", "C", "D", "E", "F"

@dataclass
class User:
    id: str
    email: str
    full_name: str
    role: UserRole
    department: str
    department_code: str = "CSE"
    password: str = "password123" # Simple authentication credential for demo/RBAC

@dataclass
class AcademicYear:
    id: int
    name: str # e.g. "2026-2027"
    start_date: date
    end_date: date
    is_current: bool = True

@dataclass
class Year:
    id: int
    name: str # "Year 1", "Year 2", "Year 3", "Year 4"
    academic_level: int # 1, 2, 3, 4

@dataclass
class Semester:
    id: int
    year_id: int
    name: str # "Semester 1", "Semester 2", ...
    term_number: int

@dataclass
class Subject:
    id: str
    code: str
    name: str
    department_id: int
    department_code: str
    semester_id: int
    weekly_hours: int = 4 # periods per week
    credits: int = 3
    is_lab: bool = False

@dataclass
class FacultyAllocation:
    id: str
    faculty_id: str # Strictly 1:1 per faculty
    subject_id: str
    department_id: int
    department_code: str
    year_id: int
    semester_id: int
    section_id: int
    section_name: str
    academic_year_id: int = 1
    allocated_by: str = "ADMIN"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class TimeSlot:
    id: int
    day_of_week: int # 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday
    day_name: str
    slot_index: int # 1, 2, 3, 4, 5, 6
    start_time: str # "09:00"
    end_time: str # "10:00"
    is_break: bool = False

@dataclass
class Classroom:
    id: int
    room_number: str
    building: str
    capacity: int = 60

@dataclass
class TimetableEntry:
    id: str
    generation_id: str
    calendar_date: Optional[str] # "YYYY-MM-DD" for Day/Year scopes
    day_of_week: int # 0..4
    day_name: str
    time_slot_id: int
    slot_index: int
    start_time: str
    end_time: str
    department_id: int
    department_code: str
    section_id: int
    section_name: str
    subject_id: str
    subject_code: str
    subject_name: str
    faculty_id: str
    faculty_name: str
    semester_id: int
    semester_name: str
    year_id: int
    year_name: str
    classroom_id: int
    classroom_name: str
    is_lab: bool = False
    is_leisure: bool = False

@dataclass
class TimetableGeneration:
    id: str
    title: str
    scope: ScheduleScope
    status: ScheduleStatus
    academic_year_id: int
    target_date: Optional[str] # for DAY scope
    created_by: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: Optional[datetime] = None
    entries: List[TimetableEntry] = field(default_factory=list)
