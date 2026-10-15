from fastapi import APIRouter
from typing import Dict, Any
from app.storage import db
from app.models import UserRole

router = APIRouter(prefix="/api/metadata", tags=["Metadata & Lookups"])

@router.get("", summary="Get System Academic Metadata")
def get_metadata() -> Dict[str, Any]:
    """
    Returns lookup data for frontend form selectors and dashboards,
    including Departments (CSE, ECE, EEE, MECH) and 6 Sections (A-F).
    """
    faculty_users = [
        {
            "id": u.id,
            "name": u.full_name,
            "email": u.email,
            "department": u.department,
            "department_code": u.department_code,
        }
        for u in db.users.values()
        if u.role == UserRole.FACULTY
    ]

    allocations_list = []
    for a in db.allocations.values():
        fac = db.users.get(a.faculty_id)
        sub = db.subjects.get(a.subject_id)
        dept = db.departments.get(a.department_id)
        sec = db.sections.get(a.section_id)
        allocations_list.append({
            "id": a.id,
            "faculty_id": a.faculty_id,
            "faculty_name": fac.full_name if fac else "Unknown",
            "subject_id": a.subject_id,
            "subject_code": sub.code if sub else "",
            "subject_name": sub.name if sub else "",
            "department_id": a.department_id,
            "department_code": dept.code if dept else a.department_code,
            "year_id": a.year_id,
            "semester_id": a.semester_id,
            "section_id": a.section_id,
            "section_name": sec.name if sec else a.section_name,
            "allocated_by": a.allocated_by,
        })

    return {
        "departments": list(db.departments.values()),
        "sections": list(db.sections.values()),
        "academic_years": list(db.academic_years.values()),
        "years": list(db.years.values()),
        "semesters": list(db.semesters.values()),
        "subjects": list(db.subjects.values()),
        "faculty": faculty_users,
        "classrooms": list(db.classrooms.values()),
        "time_slots": list(db.time_slots.values()),
        "current_allocations": allocations_list,
    }
