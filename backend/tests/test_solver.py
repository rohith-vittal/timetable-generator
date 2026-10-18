import pytest
from datetime import date
from collections import Counter

from app.models import ScheduleScope, ScheduleStatus
from app.solver import TimetableSolver
from app.storage import DataStore

@pytest.fixture
def test_db():
    return DataStore()

def test_academic_year_has_2_semesters(test_db):
    """
    User Requirement: A year have 2 semesters.
    4 Years x 2 Semesters = 8 Semesters total.
    """
    for year_id in [1, 2, 3, 4]:
        year_sems = [s for s in test_db.semesters.values() if s.year_id == year_id]
        assert len(year_sems) == 2, f"Year {year_id} must have exactly 2 semesters, found {len(year_sems)}"

    assert len(test_db.semesters) == 8

def test_faculty_allocation_1_to_1_constraint(test_db):
    """
    Crucial Constraint Test:
    Each faculty member is restricted to choosing ONLY one subject.
    Updating preference replaces previous allocation.
    """
    faculty_id = "fac-cse-01"
    
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

    # Faculty updates preference to CS101 in Section B
    alloc2 = test_db.allocate_faculty_subject(
        faculty_id=faculty_id,
        subject_id="sub-cs-101",
        department_id=1,
        year_id=1,
        semester_id=1,
        section_id=2, # Section B
    )
    assert alloc2.section_name == "B"
    assert len([a for a in test_db.allocations.values() if a.faculty_id == faculty_id]) == 1

def test_faculty_allocation_invalid_mismatch(test_db):
    with pytest.raises(ValueError, match="belongs to Semester"):
        test_db.allocate_faculty_subject(
            faculty_id="fac-cse-01",
            subject_id="sub-cs-101",
            department_id=1,
            year_id=2,
            semester_id=3,
            section_id=1,
        )

    with pytest.raises(ValueError, match="belongs to department"):
        test_db.allocate_faculty_subject(
            faculty_id="fac-cse-01",
            subject_id="sub-cs-101",
            department_id=2,
            year_id=1,
            semester_id=1,
            section_id=1,
        )

def test_schedule_timing_and_no_blank_slots(test_db):
    """
    User Requirements:
      - Day starts at 9:20 and ends at 4:10.
      - Lunch break: 12:20 to 1:10.
      - Duration of each class must be an hr (6 periods per day).
      - Don't leave the timetable blank, everything has to be filled (30 periods per week per cohort).
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

    # Group by cohort (dept, sem, sec)
    cohort_entries = {}
    for e in entries:
        key = (e.department_id, e.semester_id, e.section_id)
        cohort_entries.setdefault(key, []).append(e)

    for cohort_key, items in cohort_entries.items():
        # Exactly 30 periods (5 days * 6 periods) -> 100% filled, ZERO blanks!
        assert len(items) == 30, f"Cohort {cohort_key} must have exactly 30 filled slots, found {len(items)}"
        
        # Verify 1 hour duration for each period
        for e in items:
            start_h, start_m = map(int, e.start_time.split(":"))
            end_h, end_m = map(int, e.end_time.split(":"))
            duration_minutes = (end_h * 60 + end_m) - (start_h * 60 + start_m)
            assert duration_minutes == 60, f"Class duration must be 60 mins, found {duration_minutes} mins ({e.start_time}-{e.end_time})"

        # Verify lunch break (12:20 to 13:10) has no classes
        for e in items:
            assert not (e.start_time == "12:20" and e.end_time == "13:10")

def test_daily_lab_and_2_days_last_hour_leisure(test_db):
    """
    User Requirements:
      - Every class must have at least a lab in a day.
      - In a week every class must have any 2 days last hr leisure.
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

    # Group by cohort
    cohort_entries = {}
    for e in entries:
        key = (e.department_id, e.semester_id, e.section_id)
        cohort_entries.setdefault(key, []).append(e)

    for cohort_key, items in cohort_entries.items():
        # 1. Verify every day (Mon-Fri) has at least 1 lab session
        for day_idx in range(5):
            day_items = [e for e in items if e.day_of_week == day_idx]
            lab_items = [e for e in day_items if e.is_lab]
            assert len(lab_items) >= 2, f"Cohort {cohort_key} on day {day_idx} must have a lab session of at least 2 hrs"

        # 2. Verify in a week exactly 2 days have the last hour (Period 6: 15:10 - 16:10) as Leisure
        last_hr_items = [e for e in items if e.slot_index == 6]
        leisure_last_hr = [e for e in last_hr_items if e.is_leisure]
        assert len(leisure_last_hr) == 2, f"Cohort {cohort_key} must have exactly 2 leisure days in last hour, found {len(leisure_last_hr)}"

def test_faculty_daily_workload_3_hours(test_db):
    """
    User Requirement:
      - In a day a faculty must have 3 hrs (3 classes, or 3 hrs lab, or 2 hrs lab and 1 hr class).
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

    # Group by faculty and day
    fac_day_entries = {}
    for e in entries:
        if e.faculty_id != "fac-mentor": # exclude leisure supervisors
            key = (e.faculty_id, e.day_of_week)
            fac_day_entries.setdefault(key, []).append(e)

    for (fac_id, day_idx), items in fac_day_entries.items():
        total_hours = len(items)
        lab_hours = len([e for e in items if e.is_lab])
        class_hours = len([e for e in items if not e.is_lab and not e.is_leisure])

        # Allowed configurations: 3 classes, or 3 hrs lab, or 2 hrs lab + 1 hr class
        valid_config = (
            (class_hours == 3 and lab_hours == 0) or
            (lab_hours == 3 and class_hours == 0) or
            (lab_hours == 2 and class_hours == 1) or
            (total_hours == 3)
        )
        assert valid_config, f"Faculty {fac_id} on day {day_idx} has {total_hours}h (classes={class_hours}, lab={lab_hours})"

def test_multi_department_and_6_sections_conflict_freedom(test_db):
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

    # 1. No cohort double-booking
    cohort_slots = Counter((e.day_of_week, e.time_slot_id, e.department_id, e.semester_id, e.section_id) for e in entries)
    assert max(cohort_slots.values()) == 1

    # 2. No classroom double-booking (excluding leisure in open grounds)
    teaching_entries = [e for e in entries if not e.is_leisure]
    room_slots = Counter((e.day_of_week, e.time_slot_id, e.classroom_id) for e in teaching_entries)
    assert max(room_slots.values()) == 1

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
    entries = solver.solve(generation_id="gen-test-day", scope=ScheduleScope.DAY, target_date=target_date)
    assert len(entries) > 0
    assert all(e.calendar_date == target_date for e in entries)
    assert all(e.day_of_week == 0 for e in entries)

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
        academic_year_end=date(2026, 9, 30),
    )
    assert len(entries) > 0
    assert all(e.calendar_date is not None for e in entries)
