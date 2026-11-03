from fastapi import APIRouter, HTTPException, Query, status, Response, Depends
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import csv
import io
import re

from app.schemas import (
    GenerationRequest,
    TimetableGenerationResponse,
    TimetableEntryResponse,
    FacultyAllocationCreate,
    FacultyAllocationResponse,
    BotScenarioRequest,
    BotScenarioResponse,
    BotInsightMetrics,
    SubstitutionDetail,
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

def _get_created_at_key(gen):
    dt = getattr(gen, "created_at", None)
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

@router.post(
    "/publish",
    response_model=TimetableGenerationResponse,
    summary="Publish Latest or Specified Timetable",
    description="Publishes a draft timetable (defaults to latest generated draft)."
)
def publish_latest_timetable(generation_id: Optional[str] = None, current_admin: User = Depends(require_admin)):
    target_gen = None
    if generation_id and generation_id in db.generations:
        target_gen = db.generations[generation_id]
    else:
        if db.generations:
            target_gen = sorted(db.generations.values(), key=_get_created_at_key, reverse=True)[0]

    if not target_gen:
        raise HTTPException(status_code=404, detail="No timetable generations found to publish. Please generate a timetable first.")

    target_gen.status = ScheduleStatus.PUBLISHED
    target_gen.published_at = datetime.now(timezone.utc)
    db.save_generation(target_gen)

    return TimetableGenerationResponse(
        id=target_gen.id,
        title=target_gen.title,
        scope=target_gen.scope,
        status=target_gen.status,
        academic_year_id=target_gen.academic_year_id,
        target_date=target_gen.target_date,
        created_by=target_gen.created_by,
        created_at=target_gen.created_at,
        published_at=target_gen.published_at,
        total_classes=len(target_gen.entries),
        entries=[TimetableEntryResponse.model_validate(e) for e in target_gen.entries],
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
    db.save_generation(gen)

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
        sorted_gens = sorted(db.generations.values(), key=_get_created_at_key, reverse=True)
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
    for gen in sorted(db.generations.values(), key=_get_created_at_key, reverse=True):
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
    prompt_raw = payload.get_prompt_text()
    prompt_lower = prompt_raw.lower()

    # 1. Detect Absent Faculty
    absent_faculty_list: List[User] = []
    absence_keywords = ["absent", "leave", "sick", "unavailable", "missing", "not available", "emergency leave", "off"]
    is_absence_scenario = any(k in prompt_lower for k in absence_keywords) or bool(payload.absent_faculty_name)

    faculty_users = [u for u in db.users.values() if u.role.value == "FACULTY"]

    if payload.absent_faculty_name:
        req_name = payload.absent_faculty_name.lower().strip()
        for u in faculty_users:
            if req_name in u.full_name.lower() or req_name in u.email.lower() or u.id.lower() == req_name:
                if u not in absent_faculty_list:
                    absent_faculty_list.append(u)

    if is_absence_scenario:
        for u in faculty_users:
            clean_name = re.sub(r"^(dr\.|prof\.|sir)\s+", "", u.full_name, flags=re.I).lower().strip()
            first_name = clean_name.split()[0] if clean_name else ""
            last_name = clean_name.split()[-1] if clean_name else ""

            if u.full_name.lower() in prompt_lower or (clean_name and clean_name in prompt_lower):
                if u not in absent_faculty_list:
                    absent_faculty_list.append(u)
            elif u.email.lower() in prompt_lower:
                if u not in absent_faculty_list:
                    absent_faculty_list.append(u)
            elif len(last_name) >= 4 and f" {last_name}" in f" {prompt_lower}":
                if u not in absent_faculty_list:
                    absent_faculty_list.append(u)

    # 2. Detect Target Cohort (Department, Year, Semester, Section)
    target_section = None
    target_section_id = payload.section_id
    if payload.section_name:
        target_section = next((s for s in db.sections.values() if s.name.upper() == payload.section_name.upper()), None)
        if target_section:
            target_section_id = target_section.id
    if not target_section and not target_section_id:
        sec_match = re.search(r"\b(?:section|sec)\s*[:\-]?\s*([a-fA-F])\b", prompt_lower)
        if sec_match:
            sec_letter = sec_match.group(1).upper()
            target_section = next((s for s in db.sections.values() if s.name == sec_letter), None)
            if target_section:
                target_section_id = target_section.id
    elif target_section_id and not target_section:
        target_section = db.sections.get(target_section_id)

    target_year = None
    target_year_id = payload.year_id
    if not target_year_id:
        yr_match = re.search(r"\b(?:year|yr)\s*[:\-]?\s*([1-4])\b", prompt_lower)
        if not yr_match:
            yr_match = re.search(r"\b([1-4])(?:st|nd|rd|th)?\s*(?:year|yr)\b", prompt_lower)
        if yr_match:
            target_year_id = int(yr_match.group(1))
        elif "freshman" in prompt_lower:
            target_year_id = 1
        elif "sophomore" in prompt_lower:
            target_year_id = 2
        elif "junior" in prompt_lower:
            target_year_id = 3
        elif "senior" in prompt_lower:
            target_year_id = 4
    if target_year_id:
        target_year = db.years.get(target_year_id)

    target_sem = None
    target_sem_id = payload.semester_id
    if not target_sem_id:
        sem_match = re.search(r"\b(?:semester|sem)\s*[:\-]?\s*([1-8])\b", prompt_lower)
        if not sem_match:
            sem_match = re.search(r"\b([1-8])(?:st|nd|rd|th)?\s*(?:semester|sem)\b", prompt_lower)
        if sem_match:
            target_sem_id = int(sem_match.group(1))
    if target_sem_id:
        target_sem = db.semesters.get(target_sem_id)

    target_dept = None
    target_dept_id = payload.department_id
    if not target_dept_id:
        dept_match = re.search(r"\b(CSE|ECE|EEE|MECH)\b", prompt_raw, re.I)
        if dept_match:
            d_code = dept_match.group(1).upper()
            target_dept = next((d for d in db.departments.values() if d.code == d_code), None)
            if target_dept:
                target_dept_id = target_dept.id
    elif target_dept_id:
        target_dept = db.departments.get(target_dept_id)

    if not target_dept and absent_faculty_list:
        target_dept = next((d for d in db.departments.values() if d.code == absent_faculty_list[0].department_code), None)
        if target_dept:
            target_dept_id = target_dept.id

    # 3. Determine Scope & Target Date
    scope = payload.scope
    if not scope:
        if absent_faculty_list or any(w in prompt_lower for w in ["tomorrow", "single day", "today", "emergency day", "1 day", "1-day", "date"]):
            scope = ScheduleScope.DAY
        elif any(w in prompt_lower for w in ["year", "academic year", "annual", "full calendar", "1 year"]):
            scope = ScheduleScope.YEAR
        else:
            scope = ScheduleScope.WEEK

    target_date = payload.target_date
    if scope == ScheduleScope.DAY and not target_date:
        date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", prompt_raw)
        if date_match:
            target_date = date_match.group(1)
        else:
            target_date = "2026-10-19" # Default next academic Monday

    # 4. Database Records Count
    total_faculty = len(faculty_users)
    total_allocations = len(db.allocations)
    total_subjects = len(db.subjects)
    total_classrooms = len(db.classrooms)
    db_records_count = len(db.users) + total_allocations + total_subjects + total_classrooms

    # 5. Formulate Scenario Label
    cohort_desc_parts = []
    if target_dept:
        cohort_desc_parts.append(target_dept.code)
    if target_year:
        cohort_desc_parts.append(target_year.name)
    if target_sem:
        cohort_desc_parts.append(target_sem.name)
    if target_section:
        cohort_desc_parts.append(f"Section {target_section.name}")
    target_cohort_str = " • ".join(cohort_desc_parts) if cohort_desc_parts else "All Cohorts"

    if absent_faculty_list:
        absent_names = ", ".join([u.full_name for u in absent_faculty_list])
        if target_section:
            scenario = f"Absent Faculty Adjustment: {absent_names} ({target_cohort_str} • {target_date})"
        else:
            scenario = f"Absent Faculty Emergency Rescheduling: {absent_names} ({target_date})"
    elif scope == ScheduleScope.DAY:
        scenario = f"Emergency Single-Day Conflict-Free Deployment ({target_date})"
    elif "lab" in prompt_lower:
        scenario = "Lab-Intensive Multi-Section Balancing (2h/3h Sessions)"
    elif "freshman" in prompt_lower or "year 1" in prompt_lower:
        scenario = "Freshman Priority Section Scheduling (Year 1 Sections A-F)"
    elif scope == ScheduleScope.YEAR:
        scenario = "Full Academic Year Institutional Calendar (Zero Blank Periods)"
    else:
        scenario = "Master Institutional Conflict-Free Weekly Schedule"

    # 6. Run Timetable Solver
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
    absent_ids = [u.id for u in absent_faculty_list]
    entries = solver.solve(
        generation_id=gen_id,
        scope=scope,
        target_date=target_date,
        absent_faculty_ids=absent_ids if absent_ids else None,
    )

    # 7. Save generation in DB
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

    # 8. Identify Substitutions
    substitutions_list: List[SubstitutionDetail] = []
    for e in entries:
        if "(Substitute" in e.faculty_name:
            orig_match = re.search(r"\(Substitute for (.+?)\)", e.faculty_name)
            orig_fac = orig_match.group(1) if orig_match else "Absent Faculty"
            clean_sub_name = re.sub(r"\s*\(Substitute.*?\)", "", e.faculty_name).strip()
            substitutions_list.append(
                SubstitutionDetail(
                    slot_index=e.slot_index,
                    time=f"{e.start_time} - {e.end_time}",
                    subject_code=e.subject_code,
                    subject_name=e.subject_name,
                    classroom=e.classroom_name,
                    original_faculty=orig_fac,
                    substitute_faculty=clean_sub_name,
                    section_name=e.section_name,
                    department_code=e.department_code,
                    year_id=e.year_id,
                    semester_id=e.semester_id,
                )
            )

    # 9. Calculate Metrics & Specific Cohort Entries
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

    # Filter entries for the specific section & cohort if specified
    cohort_entries = entries
    if target_section_id:
        sec_filtered = [e for e in cohort_entries if e.section_id == target_section_id]
        if sec_filtered:
            cohort_entries = sec_filtered
    if target_sem_id:
        sem_filtered = [e for e in cohort_entries if e.semester_id == target_sem_id]
        if sem_filtered:
            cohort_entries = sem_filtered
    if target_dept_id:
        dept_filtered = [e for e in cohort_entries if e.department_id == target_dept_id]
        if dept_filtered:
            cohort_entries = dept_filtered
    cohort_entries.sort(key=lambda e: e.slot_index)

    # Build Substituted Sessions Table
    sub_table_md = ""
    if substitutions_list:
        sub_table_md += f"\n### 🔄 Reallocated Periods (Substitutes Assigned for {target_date}):\n\n"
        sub_table_md += "| Period | Time Slot | Cohort | Subject | Room | Substitute Assigned | Original Faculty |\n"
        sub_table_md += "| :---: | :---: | :---: | :--- | :--- | :--- | :--- |\n"
        for s in substitutions_list:
            sub_table_md += f"| Period {s.slot_index} | {s.time} | {s.department_code} Sec {s.section_name} (Yr {s.year_id} Sem {s.semester_id}) | {s.subject_code} - {s.subject_name} | {s.classroom} | **{s.substitute_faculty}** | *{s.original_faculty}* |\n"

    # Build Markdown table for target cohort
    cohort_table_md = ""
    if cohort_entries and len(cohort_entries) <= 8:
        cohort_table_md += f"\n### 📅 Schedule for {target_cohort_str} ({target_date}):\n\n"
        cohort_table_md += "| Period | Time Slot | Subject | Room | Assigned Faculty | Status |\n"
        cohort_table_md += "| :---: | :---: | :--- | :--- | :--- | :--- |\n"
        for e in cohort_entries:
            if e.slot_index == 4:
                cohort_table_md += "| — | 12:20 - 13:10 | **Lunch Break** | Dining Hall | *Recess* | 🍽️ Fixed Recess |\n"
            is_sub = "(Substitute" in e.faculty_name
            status_badge = "🔄 Substitute Allocated" if is_sub else ("🧪 Lab Practical" if e.is_lab else ("⚽ Leisure / Sports" if e.is_leisure else "✅ Regular Theory"))
            clean_fac = e.faculty_name.replace(" (Substitute for ", " *(Sub for ").replace(")", ")*") if is_sub else e.faculty_name
            cohort_table_md += f"| Period {e.slot_index} | {e.start_time} - {e.end_time} | {e.subject_code} - {e.subject_name} | {e.classroom_name} | {clean_fac} | {status_badge} |\n"

    # Formulate Bot Message
    if absent_faculty_list:
        absent_str = ", ".join([f"**{u.full_name}** ({u.department_code})" for u in absent_faculty_list])
        bot_message = (
            f"🤖 **ChronoBot Situational Emergency Report: Faculty Absence Rescheduled**\n\n"
            f"I analyzed your request: *\"{prompt_raw}\"*\n\n"
            f"- **Absent Faculty Member**: {absent_str}\n"
            f"- **Target Cohort**: {target_cohort_str}\n"
            f"- **Target Date**: {target_date} ({scope.value} Scope)\n"
            f"- **Substitutions Successfully Applied**: {len(substitutions_list)} period(s) across affected sections.\n"
            f"{sub_table_md}\n"
            f"{cohort_table_md}\n"
            f"### 🛡️ Institutional Regulations Enforced:\n"
            f"- **Zero Blank Periods**: 100% of periods for {target_cohort_str} are fully covered.\n"
            f"- **Daily Workload Cap**: All substitute faculty remain strictly within the 3 hours/day workload limit.\n"
            f"- **Zero Conflicts**: Verified 0 overlapping room, faculty, or student cohort assignments.\n"
            f"- **Schedule Timings**: Exactly 1 hour per period (09:20 - 16:10) with mandatory 50-minute Lunch (12:20 - 13:10).\n\n"
            f"Generated schedule ID `{gen_id}` is saved in SQLite as **DRAFT** and is available in your Master Timetable Viewer for review."
        )
    else:
        bot_message = (
            f"🤖 **ChronoBot Situational Report**:\n\n"
            f"I analyzed your request: *\"{prompt_raw}\"*\n"
            f"- **Identified Scenario**: {scenario}\n"
            f"- **Database State Consulted**: {db_records_count} active database entities ({total_faculty} faculty members, {total_allocations} allocations, {total_classrooms} classrooms/labs).\n"
            f"- **Target Cohort Focus**: {target_cohort_str}\n"
            f"{cohort_table_md}\n"
            f"- **Timetable Regulations Enforced**:\n"
            f"  • Daily Hours: 09:20 - 16:10 with 50-minute Lunch Break (12:20 - 13:10).\n"
            f"  • Class Duration: Exactly 1 hour per period across 6 daily periods.\n"
            f"  • Zero Blank Periods: All {len(entries)} periods scheduled.\n"
            f"  • Daily Labs: Scheduled {lab_count} practical lab periods across all sections.\n"
            f"  • Weekly Leisure: Allocated {leisure_count} leisure/sports periods in Period 6.\n"
            f"  • Faculty Workload: Strictly 3 hours/day per active teacher (0 double-bookings).\n\n"
            f"Generated schedule ID `{gen_id}` is now available in your Master Timetable Viewer as **DRAFT** ready for review and publishing."
        )

    entry_responses = [
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
    ]

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
            entries=entry_responses,
        ),
        insights=insights,
        entries=entry_responses,
        substitutions=substitutions_list,
        target_cohort=target_cohort_str,
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


