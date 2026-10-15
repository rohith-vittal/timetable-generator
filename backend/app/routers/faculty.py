from fastapi import APIRouter, HTTPException, Query, status
from typing import Optional, List
from datetime import datetime

from app.schemas import (
    FacultyAllocationCreate,
    FacultyAllocationResponse,
    TimetableEntryResponse,
)
from app.models import ScheduleScope, ScheduleStatus
from app.storage import db

router = APIRouter(prefix="/api/faculty", tags=["Faculty Interface"])

@router.post(
    "/allocate",
    response_model=FacultyAllocationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subject Allocation for Faculty",
    description="Allows a faculty member to select their teaching preference. Strictly enforces the 1:1 constraint (only one subject per faculty)."
)
def allocate_subject(payload: FacultyAllocationCreate):
    try:
        alloc = db.allocate_faculty_subject(
            faculty_id=payload.faculty_id,
            subject_id=payload.subject_id,
            department_id=payload.department_id,
            year_id=payload.year_id,
            semester_id=payload.semester_id,
            section_id=payload.section_id,
            academic_year_id=payload.academic_year_id,
            allocated_by="FACULTY",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    faculty = db.users[alloc.faculty_id]
    subject = db.subjects[alloc.subject_id]
    year = db.years[alloc.year_id]
    semester = db.semesters[alloc.semester_id]
    dept = db.departments[alloc.department_id]
    sec = db.sections[alloc.section_id]

    return FacultyAllocationResponse(
        id=alloc.id,
        faculty_id=alloc.faculty_id,
        faculty_name=faculty.full_name,
        subject_id=alloc.subject_id,
        subject_code=subject.code,
        subject_name=subject.name,
        department_id=alloc.department_id,
        department_code=dept.code,
        year_id=alloc.year_id,
        year_name=year.name,
        semester_id=alloc.semester_id,
        semester_name=semester.name,
        section_id=alloc.section_id,
        section_name=sec.name,
        allocated_by=alloc.allocated_by,
        created_at=alloc.created_at,
    )

@router.get(
    "/allocation/{faculty_id}",
    response_model=FacultyAllocationResponse,
    summary="Get Faculty's Subject Allocation",
)
def get_faculty_allocation(faculty_id: str):
    if faculty_id not in db.users:
        raise HTTPException(status_code=404, detail="Faculty member not found")

    if faculty_id not in db.faculty_allocation_map:
        raise HTTPException(status_code=404, detail="No subject allocation found for this faculty member")

    alloc_id = db.faculty_allocation_map[faculty_id]
    alloc = db.allocations[alloc_id]
    faculty = db.users[alloc.faculty_id]
    subject = db.subjects[alloc.subject_id]
    year = db.years[alloc.year_id]
    semester = db.semesters[alloc.semester_id]
    dept = db.departments[alloc.department_id]
    sec = db.sections[alloc.section_id]

    return FacultyAllocationResponse(
        id=alloc.id,
        faculty_id=alloc.faculty_id,
        faculty_name=faculty.full_name,
        subject_id=alloc.subject_id,
        subject_code=subject.code,
        subject_name=subject.name,
        department_id=alloc.department_id,
        department_code=dept.code,
        year_id=alloc.year_id,
        year_name=year.name,
        semester_id=alloc.semester_id,
        semester_name=semester.name,
        section_id=alloc.section_id,
        section_name=sec.name,
        allocated_by=alloc.allocated_by,
        created_at=alloc.created_at,
    )

@router.get(
    "/timetable/{faculty_id}",
    response_model=List[TimetableEntryResponse],
    summary="Personalized Faculty Timetable Dashboard",
    description="A read-only view where the faculty member sees their own generated timetable (daily, weekly, or yearly view) once published by admin."
)
def get_faculty_timetable(
    faculty_id: str,
    generation_id: Optional[str] = Query(None, description="Specific generation ID. If omitted, uses the latest published generation."),
    view_date: Optional[str] = Query(None, description="Filter for specific calendar date (YYYY-MM-DD)"),
    day_of_week: Optional[int] = Query(None, ge=0, le=4, description="0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri"),
):
    if faculty_id not in db.users:
        raise HTTPException(status_code=404, detail="Faculty member not found")

    target_gen = None
    if generation_id:
        target_gen = db.generations.get(generation_id)
        if not target_gen:
            raise HTTPException(status_code=404, detail="Requested timetable generation not found")
    else:
        published_gens = [
            g for g in db.generations.values()
            if g.status == ScheduleStatus.PUBLISHED
        ]
        if not published_gens:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No published timetable is currently available. Please check back once the administration publishes the schedule."
            )
        published_gens.sort(key=lambda g: g.created_at, reverse=True)
        target_gen = published_gens[0]

    # Filter entries strictly belonging to this faculty member
    faculty_entries = [
        e for e in target_gen.entries if e.faculty_id == faculty_id
    ]

    if view_date:
        faculty_entries = [e for e in faculty_entries if e.calendar_date == view_date]
    if day_of_week is not None:
        faculty_entries = [e for e in faculty_entries if e.day_of_week == day_of_week]

    return [TimetableEntryResponse.model_validate(e) for e in faculty_entries]
