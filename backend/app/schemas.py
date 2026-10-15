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
    role: UserRole
    department: str
    department_code: str

class LoginResponse(BaseModel):
    token: str
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
