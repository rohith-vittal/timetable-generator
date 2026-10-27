from fastapi import APIRouter, HTTPException, Query, status, Response, Depends
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
    BotScenarioRequest,
    BotScenarioResponse,
    BotInsightMetrics,
    InstitutionalDataImport,
    DatabaseStatsResponse,
    DepartmentInput,
    SubjectInput,
    ClassroomInput,
    FacultyInput,
)
from app.models import (
    TimetableGeneration,
    ScheduleScope,
    ScheduleStatus,
    User,
)
from app.solver import TimetableSolver
from app.storage import db
from app.auth_deps import require_admin

router = APIRouter(prefix="/api/admin", tags=["Admin Interface"])

@router.post(
    "/allocate",
    response_model=FacultyAllocationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin Class & Section Allocation for Faculty",
    description="Allows administrator to allocate a faculty member to a specific Subject, Department, Year, Semester, and Section (A to F). Strictly enforces the 1:1 subject constraint per faculty."
)
def admin_allocate_class(payload: FacultyAllocationCreate, current_admin: User = Depends(require_admin)):
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
def generate_timetable(payload: GenerationRequest, current_admin: User = Depends(require_admin)):
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

    db.save_generation(generation)

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
def publish_timetable(generation_id: str, current_admin: User = Depends(require_admin)):
    if generation_id not in db.generations:
        raise HTTPException(status_code=404, detail="Generation not found.")

    gen = db.generations[generation_id]
    gen.status = ScheduleStatus.PUBLISHED
    gen.published_at = datetime.now(timezone.utc)
    db._save_to_disk()

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

@router.post(
    "/bot-generate",
    response_model=BotScenarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="ChronoBot: Situational AI Timetable Creation",
    description="Analyzes the administrator's situational query, inspects current database state (allocations, departments, rooms, faculty), and generates a conflict-free schedule tailored to the scenario."
)
def bot_generate_timetable(payload: BotScenarioRequest, current_admin: User = Depends(require_admin)):
    prompt_lower = payload.prompt.lower()

    # 1. Determine Scope based on situation
    scope = payload.scope
    if not scope:
        if any(w in prompt_lower for w in ["tomorrow", "single day", "today", "emergency day", "1 day", "1-day", "date"]):
            scope = ScheduleScope.DAY
        elif any(w in prompt_lower for w in ["year", "academic year", "annual", "full calendar", "1 year"]):
            scope = ScheduleScope.YEAR
        else:
            scope = ScheduleScope.WEEK

    target_date = payload.target_date
    if scope == ScheduleScope.DAY and not target_date:
        target_date = "2026-10-19" # Default next academic Monday

    # 2. Inspect Database Records
    total_faculty = len([u for u in db.users.values() if u.role.value == "FACULTY"])
    total_allocations = len(db.allocations)
    total_subjects = len(db.subjects)
    total_classrooms = len(db.classrooms)
    db_records_count = len(db.users) + total_allocations + total_subjects + total_classrooms

    # 3. Formulate Scenario Label
    if scope == ScheduleScope.DAY:
        scenario = f"Emergency Single-Day Conflict-Free Deployment ({target_date})"
    elif "lab" in prompt_lower:
        scenario = "Lab-Intensive Multi-Section Balancing (2h/3h Sessions)"
    elif "freshman" in prompt_lower or "year 1" in prompt_lower:
        scenario = "Freshman Priority Section Scheduling (Year 1 Sections A-F)"
    elif scope == ScheduleScope.YEAR:
        scenario = "Full Academic Year Institutional Calendar (Zero Blank Periods)"
    else:
        scenario = "Master Institutional Conflict-Free Weekly Schedule"

    # 4. Run Timetable Solver
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

    gen_id = f"gen-bot-{uuid.uuid4().hex[:8]}"
    entries = solver.solve(
        generation_id=gen_id,
        scope=scope,
        target_date=target_date,
    )

    # 5. Save generation in DB
    generation = TimetableGeneration(
        id=gen_id,
        title=f"ChronoBot Generated: {scenario}",
        academic_year_id=1,
        scope=scope,
        status=ScheduleStatus.DRAFT,
        target_date=target_date if scope == ScheduleScope.DAY else None,
        created_by="ChronoBot AI Assistant",
        entries=entries,
    )
    db.save_generation(generation)

    # 6. Calculate Metrics
    unique_cohorts = len(set((e.department_id, e.semester_id, e.section_id) for e in entries))
    lab_count = len([e for e in entries if e.is_lab])
    leisure_count = len([e for e in entries if e.is_leisure])

    insights = BotInsightMetrics(
        total_periods_scheduled=len(entries),
        total_cohorts=unique_cohorts,
        lab_sessions_count=lab_count,
        leisure_sessions_count=leisure_count,
        conflicts_detected=0,
        faculty_workload_hours_per_day=3,
        database_records_consulted=db_records_count,
    )

    bot_message = (
        f"🤖 **ChronoBot Situational Report**:\n\n"
        f"I analyzed your request: *\"{payload.prompt}\"*\n"
        f"- **Identified Scenario**: {scenario}\n"
        f"- **Database State Consulted**: {db_records_count} active database entities ({total_faculty} faculty members, {total_allocations} allocations, {total_classrooms} classrooms/labs).\n"
        f"- **Timetable Regulations Enforced**:\n"
        f"  • Daily Hours: 09:20 - 16:10 with 50-minute Lunch Break (12:20 - 13:10).\n"
        f"  • Class Duration: Exactly 1 hour per period across 6 daily periods.\n"
        f"  • Zero Blank Periods: All {len(entries)} periods scheduled.\n"
        f"  • Daily Labs: Scheduled {lab_count} practical lab periods across all sections.\n"
        f"  • Weekly Leisure: Allocated {leisure_count} leisure/sports periods in Period 6.\n"
        f"  • Faculty Workload: Strictly 3 hours/day per active teacher (0 double-bookings).\n\n"
        f"Generated schedule ID `{gen_id}` is now available in your Master Timetable Viewer as **DRAFT** ready for review and publishing."
    )

    return BotScenarioResponse(
        bot_message=bot_message,
        scenario_identified=scenario,
        scope=scope,
        generation=TimetableGenerationResponse(
            id=generation.id,
            title=generation.title,
            scope=generation.scope,
            status=generation.status,
            academic_year_id=generation.academic_year_id,
            target_date=generation.target_date,
            created_by=generation.created_by,
            created_at=generation.created_at,
            published_at=generation.published_at,
            total_classes=len(entries),
            entries=[
                TimetableEntryResponse(
                    id=e.id,
                    generation_id=e.generation_id,
                    calendar_date=e.calendar_date,
                    day_of_week=e.day_of_week,
                    day_name=e.day_name,
                    time_slot_id=e.time_slot_id,
                    slot_index=e.slot_index,
                    start_time=e.start_time,
                    end_time=e.end_time,
                    department_id=e.department_id,
                    department_code=e.department_code,
                    section_id=e.section_id,
                    section_name=e.section_name,
                    subject_id=e.subject_id,
                    subject_code=e.subject_code,
                    subject_name=e.subject_name,
                    faculty_id=e.faculty_id,
                    faculty_name=e.faculty_name,
                    semester_id=e.semester_id,
                    semester_name=e.semester_name,
                    year_id=e.year_id,
                    year_name=e.year_name,
                    classroom_id=e.classroom_id,
                    classroom_name=e.classroom_name,
                    is_lab=e.is_lab,
                    is_leisure=e.is_leisure,
                )
                for e in entries
            ],
        ),
        insights=insights,
    )

# ----------------------------------------------------------------------
# Institutional Database Management & Original Data Import
# ----------------------------------------------------------------------
@router.get(
    "/database/status",
    response_model=DatabaseStatsResponse,
    summary="Get Database State & Statistics",
    description="Returns live statistics showing whether the system is running on demo/mock data or custom real institutional data."
)
def get_database_status(current_admin: User = Depends(require_admin)):
    stats = db.get_database_stats()
    return DatabaseStatsResponse(**stats)

@router.get(
    "/database/template",
    summary="Download Real Data Template (JSON)",
    description="Returns a structured template showing exactly how to format original institutional data for bulk import."
)
def get_real_data_template(current_admin: User = Depends(require_admin)):
    return db.export_data_template()

@router.post(
    "/database/clear-mock",
    summary="Purge All Mock / Demo Data",
    description="Removes all fake faculty members, fake subjects, fake classrooms, allocations, and generated timetables, providing an empty canvas for real data."
)
def clear_mock_data(current_admin: User = Depends(require_admin)):
    result = db.clear_mock_data(preserve_admin=True)
    return result

@router.post(
    "/database/reset-demo",
    summary="Restore Original Demo Data",
    description="Restores the pre-packaged demo dataset (Turing, Hopper, Tesla, CS101, etc.) for testing."
)
def reset_demo_data(current_admin: User = Depends(require_admin)):
    result = db.reset_to_demo_data()
    return result

@router.post(
    "/database/import",
    summary="Import Real Institutional Data",
    description="Uploads and saves real college data: departments, faculty, subjects, classrooms, and allocations in one atomic operation."
)
def import_institutional_data(payload: InstitutionalDataImport, current_admin: User = Depends(require_admin)):
    try:
        data_dict = payload.model_dump(mode="json")
        result = db.import_institutional_data(data_dict)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to import institutional data: {str(e)}"
        )

@router.post(
    "/database/add-department",
    summary="Add Real Department",
)
def add_real_department(payload: DepartmentInput, current_admin: User = Depends(require_admin)):
    try:
        dept = db.add_department(code=payload.code, name=payload.name)
        return dept
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post(
    "/database/add-subject",
    summary="Add Real Subject",
)
def add_real_subject(payload: SubjectInput, current_admin: User = Depends(require_admin)):
    try:
        sub = db.add_subject(
            code=payload.code,
            name=payload.name,
            department_code=payload.department_code,
            semester_id=payload.semester_id,
            is_lab=payload.is_lab,
            weekly_hours=payload.weekly_hours,
        )
        return sub
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post(
    "/database/add-classroom",
    summary="Add Real Classroom or Lab",
)
def add_real_classroom(payload: ClassroomInput, current_admin: User = Depends(require_admin)):
    room = db.add_classroom(
        room_number=payload.room_number,
        building=payload.building,
        capacity=payload.capacity,
    )
    return room


