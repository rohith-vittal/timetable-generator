from fastapi import APIRouter, HTTPException, Query, status, Response
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import csv
import io

from app.schemas import (
    GenerationRequest,
    TimetableGenerationResponse,
    TimetableEntryResponse,
    FacultyAllocationCreate,
    FacultyAllocationResponse,
)
from app.models import (
    TimetableGeneration,
    ScheduleScope,
    ScheduleStatus,
)
from app.solver import TimetableSolver
from app.storage import db

router = APIRouter(prefix="/api/admin", tags=["Admin Interface"])

@router.post(
    "/allocate",
    response_model=FacultyAllocationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin Class & Section Allocation for Faculty",
    description="Allows administrator to allocate a faculty member to a specific Subject, Department, Year, Semester, and Section (A to F). Strictly enforces the 1:1 subject constraint per faculty."
)
def admin_allocate_class(payload: FacultyAllocationCreate):
    try:
        alloc = db.allocate_faculty_subject(
            faculty_id=payload.faculty_id,
            subject_id=payload.subject_id,
            department_id=payload.department_id,
            year_id=payload.year_id,
            semester_id=payload.semester_id,
            section_id=payload.section_id,
            academic_year_id=payload.academic_year_id,
            allocated_by="ADMIN",
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

@router.post(
    "/generate",
    response_model=TimetableGenerationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger Automated Timetable Generation Engine",
    description="Generates conflict-free timetable across all departments (CSE, ECE, EEE, MECH) and sections (A-F) for the chosen scope (DAY, WEEK, or YEAR)."
)
def generate_timetable(payload: GenerationRequest):
    if payload.scope == ScheduleScope.DAY and not payload.target_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_date (YYYY-MM-DD) is required when generation scope is 'DAY'."
        )

    # Initialize Solver with departments and sections
    solver = TimetableSolver(
        subjects=list(db.subjects.values()),
        allocations=list(db.allocations.values()),
        time_slots=list(db.time_slots.values()),
        classrooms=list(db.classrooms.values()),
        users=db.users,
        semesters=db.semesters,
        years=db.years,
        departments=db.departments,
        sections=db.sections,
    )

    gen_id = f"gen-{uuid.uuid4().hex[:8]}"

    try:
        entries = solver.solve(
            generation_id=gen_id,
            scope=payload.scope,
            target_date=payload.target_date,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Scheduling engine constraint error: {str(e)}"
        )

    generation = TimetableGeneration(
        id=gen_id,
        title=payload.title,
        scope=payload.scope,
        status=ScheduleStatus.DRAFT,
        academic_year_id=payload.academic_year_id,
        target_date=payload.target_date,
        created_by="u-admin-001",
        created_at=datetime.now(timezone.utc),
        entries=entries,
    )

    db.generations[gen_id] = generation

    return TimetableGenerationResponse(
        id=generation.id,
        title=generation.title,
        scope=generation.scope,
        status=generation.status,
        academic_year_id=generation.academic_year_id,
        target_date=generation.target_date,
        created_by=generation.created_by,
        created_at=generation.created_at,
        published_at=generation.published_at,
        total_classes=len(generation.entries),
        entries=[TimetableEntryResponse.model_validate(e) for e in generation.entries],
    )

@router.post(
    "/publish/{generation_id}",
    response_model=TimetableGenerationResponse,
    summary="Publish Timetable",
    description="Publishes a draft timetable, making it live and accessible to all faculty dashboards."
)
def publish_timetable(generation_id: str):
    if generation_id not in db.generations:
        raise HTTPException(status_code=404, detail="Generation not found.")

    gen = db.generations[generation_id]
    gen.status = ScheduleStatus.PUBLISHED
    gen.published_at = datetime.now(timezone.utc)

    return TimetableGenerationResponse(
        id=gen.id,
        title=gen.title,
        scope=gen.scope,
        status=gen.status,
        academic_year_id=gen.academic_year_id,
        target_date=gen.target_date,
        created_by=gen.created_by,
        created_at=gen.created_at,
        published_at=gen.published_at,
        total_classes=len(gen.entries),
        entries=[TimetableEntryResponse.model_validate(e) for e in gen.entries],
    )

@router.get(
    "/timetables",
    response_model=List[TimetableEntryResponse],
    summary="Global Timetable Viewer with Multi-Department & Section Filtering",
    description="Master viewer for administrators. Allows filtering by Department, Year, Semester, Section, and Faculty member."
)
def get_global_timetable(
    generation_id: Optional[str] = Query(None, description="Generation ID. Defaults to latest generation if omitted."),
    department_id: Optional[int] = Query(None, description="Filter by Department (1=CSE, 2=ECE, 3=EEE, 4=MECH)"),
    year_id: Optional[int] = Query(None, description="Filter by Year (1, 2, 3, 4)"),
    semester_id: Optional[int] = Query(None, description="Filter by Semester (1, 3, 5, 7)"),
    section_id: Optional[int] = Query(None, description="Filter by Section (1 to 6 for Sections A to F)"),
    faculty_id: Optional[str] = Query(None, description="Filter by Faculty Member UUID"),
    day_of_week: Optional[int] = Query(None, ge=0, le=4, description="Filter by Day (0=Mon ... 4=Fri)"),
):
    target_gen = None
    if generation_id:
        target_gen = db.generations.get(generation_id)
        if not target_gen:
            raise HTTPException(status_code=404, detail="Generation not found.")
    else:
        if not db.generations:
            return []
        sorted_gens = sorted(db.generations.values(), key=lambda g: g.created_at, reverse=True)
        target_gen = sorted_gens[0]

    filtered_entries = target_gen.entries

    if department_id is not None:
        filtered_entries = [e for e in filtered_entries if e.department_id == department_id]

    if year_id is not None:
        filtered_entries = [e for e in filtered_entries if e.year_id == year_id]

    if semester_id is not None:
        filtered_entries = [e for e in filtered_entries if e.semester_id == semester_id]

    if section_id is not None:
        filtered_entries = [e for e in filtered_entries if e.section_id == section_id]

    if faculty_id:
        filtered_entries = [e for e in filtered_entries if e.faculty_id == faculty_id]

    if day_of_week is not None:
        filtered_entries = [e for e in filtered_entries if e.day_of_week == day_of_week]

    return [TimetableEntryResponse.model_validate(e) for e in filtered_entries]

@router.get(
    "/generations",
    response_model=List[TimetableGenerationResponse],
    summary="List All Generated Timetables",
)
def list_generations():
    results = []
    for gen in sorted(db.generations.values(), key=lambda g: g.created_at, reverse=True):
        results.append(
            TimetableGenerationResponse(
                id=gen.id,
                title=gen.title,
                scope=gen.scope,
                status=gen.status,
                academic_year_id=gen.academic_year_id,
                target_date=gen.target_date,
                created_by=gen.created_by,
                created_at=gen.created_at,
                published_at=gen.published_at,
                total_classes=len(gen.entries),
                entries=[],
            )
        )
    return results

@router.get(
    "/timetables/{generation_id}/export",
    summary="Export Timetable as CSV",
    description="Exports the timetable entries in standardized CSV format with Department and Section columns."
)
def export_timetable_csv(generation_id: str):
    if generation_id not in db.generations:
        raise HTTPException(status_code=404, detail="Generation not found.")

    gen = db.generations[generation_id]

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Entry ID",
        "Calendar Date",
        "Day",
        "Time Slot",
        "Start Time",
        "End Time",
        "Department",
        "Section",
        "Year",
        "Semester",
        "Subject Code",
        "Subject Name",
        "Faculty Member",
        "Classroom",
    ])

    for e in gen.entries:
        writer.writerow([
            e.id,
            e.calendar_date or "Recurring Weekly",
            e.day_name,
            f"Period {e.slot_index}",
            e.start_time,
            e.end_time,
            e.department_code,
            f"Section {e.section_name}",
            e.year_name,
            e.semester_name,
            e.subject_code,
            e.subject_name,
            e.faculty_name,
            e.classroom_name,
        ])

    csv_data = output.getvalue()
    filename = f"timetable_{gen.title.replace(' ', '_')}_{gen.scope}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
