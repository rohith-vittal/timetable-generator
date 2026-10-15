import pytest
from datetime import date
from collections import Counter

from app.models import ScheduleScope, ScheduleStatus
from app.solver import TimetableSolver
from app.storage import DataStore

@pytest.fixture
def test_db():
    return DataStore()

def test_faculty_allocation_1_to_1_constraint(test_db):
    """
    Crucial Constraint Test:
    Each faculty member is restricted to choosing ONLY one subject.
    Updating preference replaces previous allocation.
    """
    faculty_id = "fac-cse-01"
    
    # Initial allocation is CS101, CSE, Yr 1, Sem 1, Sec A
    alloc1 = test_db.allocate_faculty_subject(
        faculty_id=faculty_id,
        subject_id="sub-cs-101",
        department_id=1,
        year_id=1,
        semester_id=1,
        section_id=1,
    )
    assert alloc1.subject_id == "sub-cs-101"
    assert alloc1.section_name == "A"
    assert len([a for a in test_db.allocations.values() if a.faculty_id == faculty_id]) == 1

    # Admin re-allocates faculty to CS101 in Section B
    alloc2 = test_db.allocate_faculty_subject(
        faculty_id=faculty_id,
        subject_id="sub-cs-101",
        department_id=1,
        year_id=1,
        semester_id=1,
        section_id=2, # Section B
    )
    assert alloc2.section_name == "B"
    # Strict 1:1: Still only 1 allocation exists for this faculty member!
    assert len([a for a in test_db.allocations.values() if a.faculty_id == faculty_id]) == 1

def test_faculty_allocation_invalid_mismatch(test_db):
    """
    Test that assigning a subject to an incompatible semester or department is rejected.
    """
    with pytest.raises(ValueError, match="belongs to Semester"):
        # sub-cs-101 belongs to Semester 1, not Semester 3
        test_db.allocate_faculty_subject(
            faculty_id="fac-cse-01",
            subject_id="sub-cs-101",
            department_id=1,
            year_id=2,
            semester_id=3,
            section_id=1,
        )

    with pytest.raises(ValueError, match="belongs to department"):
        # sub-cs-101 belongs to CSE, not ECE (dept_id=2)
        test_db.allocate_faculty_subject(
            faculty_id="fac-cse-01",
            subject_id="sub-cs-101",
            department_id=2,
            year_id=1,
            semester_id=1,
            section_id=1,
        )

def test_multi_department_and_6_sections_conflict_freedom(test_db):
    """
    Test that a generated weekly timetable has ZERO conflicts across:
    - Multiple Departments (CSE, ECE, EEE, MECH)
    - 6 Sections (A through F)
    - No faculty overlap
    - No section cohort overlap (Dept + Semester + Section)
    - No classroom overlap
    - No classes in lunch break
    """
    solver = TimetableSolver(
        subjects=list(test_db.subjects.values()),
        allocations=list(test_db.allocations.values()),
        time_slots=list(test_db.time_slots.values()),
        classrooms=list(test_db.classrooms.values()),
        users=test_db.users,
        semesters=test_db.semesters,
        years=test_db.years,
        departments=test_db.departments,
        sections=test_db.sections,
    )

    entries = solver.solve(generation_id="gen-test-week", scope=ScheduleScope.WEEK)
    assert len(entries) > 0

    # 1. Check Faculty Conflict: No faculty in two places at once
    faculty_slot_pairs = [(e.day_of_week, e.time_slot_id, e.faculty_id) for e in entries]
    faculty_counts = Counter(faculty_slot_pairs)
    duplicate_faculty = [k for k, v in faculty_counts.items() if v > 1]
    assert len(duplicate_faculty) == 0, f"Faculty conflict detected: {duplicate_faculty}"

    # 2. Check Cohort Conflict: (Department, Semester, Section) cannot have 2 classes at once
    cohort_slot_pairs = [(e.day_of_week, e.time_slot_id, e.department_id, e.semester_id, e.section_id) for e in entries]
    cohort_counts = Counter(cohort_slot_pairs)
    duplicate_cohorts = [k for k, v in cohort_counts.items() if v > 1]
    assert len(duplicate_cohorts) == 0, f"Cohort/Section conflict detected: {duplicate_cohorts}"

    # 3. Check Classroom Conflict: No room double-booking
    classroom_slot_pairs = [(e.day_of_week, e.time_slot_id, e.classroom_id) for e in entries]
    classroom_counts = Counter(classroom_slot_pairs)
    duplicate_classrooms = [k for k, v in classroom_counts.items() if v > 1]
    assert len(duplicate_classrooms) == 0, f"Classroom conflict detected: {duplicate_classrooms}"

    # 4. Check Break Exclusion: No class in period 4 (Lunch)
    lunch_entries = [e for e in entries if e.slot_index == 4]
    assert len(lunch_entries) == 0, "Classes were scheduled during lunch break!"

    # 5. Verify representation of multiple departments and sections
    depts_present = set(e.department_code for e in entries)
    assert "CSE" in depts_present
    assert "ECE" in depts_present
    assert "EEE" in depts_present
    assert "MECH" in depts_present

    sections_present = set(e.section_name for e in entries)
    assert len(sections_present) >= 4

def test_day_generation_scope(test_db):
    solver = TimetableSolver(
        subjects=list(test_db.subjects.values()),
        allocations=list(test_db.allocations.values()),
        time_slots=list(test_db.time_slots.values()),
        classrooms=list(test_db.classrooms.values()),
        users=test_db.users,
        semesters=test_db.semesters,
        years=test_db.years,
        departments=test_db.departments,
        sections=test_db.sections,
    )

    target_date = "2026-10-19" # Monday
    entries = solver.solve(
        generation_id="gen-test-day",
        scope=ScheduleScope.DAY,
        target_date=target_date,
    )

    assert len(entries) > 0
    for e in entries:
        assert e.calendar_date == target_date
        assert e.day_of_week == 0 # Monday

    # Verify conflict-freedom for the day
    faculty_slots = Counter((e.time_slot_id, e.faculty_id) for e in entries)
    assert max(faculty_slots.values()) == 1

def test_year_generation_scope(test_db):
    solver = TimetableSolver(
        subjects=list(test_db.subjects.values()),
        allocations=list(test_db.allocations.values()),
        time_slots=list(test_db.time_slots.values()),
        classrooms=list(test_db.classrooms.values()),
        users=test_db.users,
        semesters=test_db.semesters,
        years=test_db.years,
        departments=test_db.departments,
        sections=test_db.sections,
    )

    entries = solver.solve(
        generation_id="gen-test-year",
        scope=ScheduleScope.YEAR,
        academic_year_start=date(2026, 9, 1),
        academic_year_end=date(2026, 9, 30), # 1 month sample
    )

    assert len(entries) > 0
    assert all(e.calendar_date is not None for e in entries)

    date_fac_slots = Counter((e.calendar_date, e.time_slot_id, e.faculty_id) for e in entries)
    assert max(date_fac_slots.values()) == 1
