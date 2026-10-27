from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import date, datetime
from app.models import ScheduleScope, ScheduleStatus, UserRole

# -------------------------------------------------------------
# Authentication Schemas
# -------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str = Field(..., json_schema_extra={"example": "admin@university.edu"})
    password: str = Field(..., json_schema_extra={"example": "admin123"})

class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    name: Optional[str] = None
    role: UserRole
    department: str
    department_code: str

class LoginResponse(BaseModel):
    token: str
    access_token: Optional[str] = None
    user: UserProfile

# -------------------------------------------------------------
# Faculty Allocation Schemas (Admin & Faculty)
# -------------------------------------------------------------
class FacultyAllocationCreate(BaseModel):
    faculty_id: str = Field(..., description="UUID of the faculty member")
    subject_id: str = Field(..., description="UUID of the chosen subject")
    department_id: int = Field(default=1, description="Department ID (e.g. 1 for CSE)")
    year_id: int = Field(..., description="Year ID (e.g. 1 for Year 1)")
    semester_id: int = Field(..., description="Semester ID (e.g. 1 for Semester 1)")
    section_id: int = Field(default=1, description="Section ID (1 to 6 for Sections A to F)")
    academic_year_id: int = Field(default=1, description="Academic Year ID")
    allocated_by: str = Field(default="ADMIN", description="'ADMIN' or 'FACULTY'")

class FacultyAllocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    faculty_id: str
    faculty_name: str
    subject_id: str
    subject_code: str
    subject_name: str
    department_id: int
    department_code: str
    year_id: int
    year_name: str
    semester_id: int
    semester_name: str
    section_id: int
    section_name: str
    allocated_by: str
    created_at: datetime

# -------------------------------------------------------------
# Timetable Generation Request
# -------------------------------------------------------------
class GenerationRequest(BaseModel):
    title: str = Field(..., json_schema_extra={"example": "Fall 2026 Master Timetable"})
    scope: ScheduleScope = Field(..., description="Scope: DAY, WEEK, or YEAR")
    target_date: Optional[str] = Field(None, json_schema_extra={"example": "2026-10-19"}, description="Required if scope is DAY")
    academic_year_id: int = Field(default=1)

# -------------------------------------------------------------
# Timetable Entry Response
# -------------------------------------------------------------
class TimetableEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    generation_id: str
    calendar_date: Optional[str] = None
    day_of_week: int
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

# -------------------------------------------------------------
# Generation Details Response
# -------------------------------------------------------------
class TimetableGenerationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    scope: ScheduleScope
    status: ScheduleStatus
    academic_year_id: int
    target_date: Optional[str] = None
    created_by: str
    created_at: datetime
    published_at: Optional[datetime] = None
    total_classes: int
    entries: List[TimetableEntryResponse] = []

# -------------------------------------------------------------
# Admin Filter Request
# -------------------------------------------------------------
class TimetableFilterParams(BaseModel):
    department_id: Optional[int] = None
    year_id: Optional[int] = None
    semester_id: Optional[int] = None
    section_id: Optional[int] = None
    faculty_id: Optional[str] = None
    scope: Optional[ScheduleScope] = None
    calendar_date: Optional[str] = None

# -------------------------------------------------------------
# User Registration Schema
# -------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: str = Field(..., json_schema_extra={"example": "new.faculty@univ.edu"})
    password: str = Field(..., json_schema_extra={"example": "faculty123"})
    full_name: str = Field(..., json_schema_extra={"example": "Dr. Sarah Connor"})
    role: UserRole = Field(default=UserRole.FACULTY, description="User role: 'FACULTY' or 'ADMIN'")
    department_id: Optional[int] = Field(default=1, description="Department ID (1: CSE, 2: ECE, 3: EEE, 4: MECH)")

# -------------------------------------------------------------
# Bot Situational Timetable Creation Schemas
# -------------------------------------------------------------
class BotScenarioRequest(BaseModel):
    prompt: str = Field(..., json_schema_extra={"example": "Create an emergency conflict-free schedule for tomorrow with 0 blank slots and balanced labs"})
    scope: Optional[ScheduleScope] = Field(default=None, description="Optional override. Auto-detected from prompt if omitted.")
    target_date: Optional[str] = Field(default=None, json_schema_extra={"example": "2026-10-19"}, description="Required if scope is DAY")
    department_id: Optional[int] = Field(default=None, description="Optional department filter focus")

class BotInsightMetrics(BaseModel):
    total_periods_scheduled: int
    total_cohorts: int
    lab_sessions_count: int
    leisure_sessions_count: int
    conflicts_detected: int = 0
    faculty_workload_hours_per_day: int = 3
    database_records_consulted: int

class BotScenarioResponse(BaseModel):
    bot_message: str
    scenario_identified: str
    scope: ScheduleScope
    generation: TimetableGenerationResponse
    insights: BotInsightMetrics

# -------------------------------------------------------------
# Institutional Real Data Import & Database Management Schemas
# -------------------------------------------------------------
class DepartmentInput(BaseModel):
    code: str = Field(..., json_schema_extra={"example": "CSE"})
    name: str = Field(..., json_schema_extra={"example": "Computer Science & Engineering"})

class FacultyInput(BaseModel):
    full_name: str = Field(..., json_schema_extra={"example": "Dr. Sarah Connor"})
    email: str = Field(..., json_schema_extra={"example": "sarah.connor@college.edu"})
    department_code: str = Field(..., json_schema_extra={"example": "CSE"})
    password: Optional[str] = Field(default="faculty123", json_schema_extra={"example": "faculty123"})

class SubjectInput(BaseModel):
    code: str = Field(..., json_schema_extra={"example": "CS101"})
    name: str = Field(..., json_schema_extra={"example": "Programming Fundamentals"})
    department_code: str = Field(..., json_schema_extra={"example": "CSE"})
    semester_id: int = Field(..., json_schema_extra={"example": 1}, description="Semester number 1 to 8")
    weekly_hours: int = Field(default=3, description="Weekly hours (typically 3 or 4)")
    is_lab: bool = Field(default=False, description="True if laboratory practical session")

class ClassroomInput(BaseModel):
    room_number: str = Field(..., json_schema_extra={"example": "LH-101 (Lecture Hall)"})
    building: str = Field(default="Main Academic Block", json_schema_extra={"example": "Block A"})
    capacity: int = Field(default=60)

class AllocationInput(BaseModel):
    faculty_email: str = Field(..., json_schema_extra={"example": "sarah.connor@college.edu"})
    subject_code: str = Field(..., json_schema_extra={"example": "CS101"})
    section_name: str = Field(default="A", json_schema_extra={"example": "A"})
    year_id: Optional[int] = Field(default=None)
    semester_id: Optional[int] = Field(default=None)

class InstitutionalDataImport(BaseModel):
    clear_existing_mock_data: bool = Field(default=True, description="Whether to purge mock faculty, subjects, and rooms first")
    admin_email: Optional[str] = Field(default=None, description="Optional custom admin email")
    admin_password: Optional[str] = Field(default=None, description="Optional custom admin password")
    admin_name: Optional[str] = Field(default=None, description="Optional custom admin name")
    departments: Optional[List[DepartmentInput]] = Field(default=None, description="Real college departments")
    faculty: List[FacultyInput] = Field(..., description="Real college faculty list")
    subjects: List[SubjectInput] = Field(..., description="Real curriculum subjects")
    classrooms: Optional[List[ClassroomInput]] = Field(default=None, description="Real lecture halls and lab rooms")
    allocations: Optional[List[AllocationInput]] = Field(default=None, description="Initial subject-faculty assignments")

class DatabaseStatsResponse(BaseModel):
    total_departments: int
    total_sections: int
    total_faculty: int
    total_subjects: int
    total_classrooms: int
    total_allocations: int
    total_generations: int
    is_demo_mode: bool
    status: str
    message: str
    database_engine: Optional[str] = "SQLite (SQLAlchemy Relational)"
    database_target: Optional[str] = None


