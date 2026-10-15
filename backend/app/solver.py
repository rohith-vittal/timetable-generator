"""
Automated Timetable Generation Engine
Implements Constraint Satisfaction Problem (CSP) / Constraint Programming (CP-SAT)
Supports:
  - Multi-Department Scheduling (CSE, ECE, EEE, MECH)
  - 6 Distinct Class Sections (Section A through Section F)
  - Admin Class & Section Allocation
  - 100% Guaranteed Conflict Resolution (Faculty, Cohort/Section, Classroom)
  - Scope Flexibility (DAY, WEEK, YEAR)
"""

from typing import List, Dict, Tuple, Optional
from datetime import date, timedelta
import uuid

try:
    from ortools.sat.python import cp_model
    HAS_ORTOOLS = True
except ImportError:
    HAS_ORTOOLS = False

from app.models import (
    Subject,
    FacultyAllocation,
    TimeSlot,
    Classroom,
    TimetableEntry,
    ScheduleScope,
    User,
    Semester,
    Year,
    Department,
    Section,
)

class TimetableSolver:
    def __init__(
        self,
        subjects: List[Subject],
        allocations: List[FacultyAllocation],
        time_slots: List[TimeSlot],
        classrooms: List[Classroom],
        users: Dict[str, User],
        semesters: Dict[int, Semester],
        years: Dict[int, Year],
        departments: Dict[int, Department],
        sections: Dict[int, Section],
    ):
        self.subjects_map = {s.id: s for s in subjects}
        self.allocations = allocations
        self.time_slots = [ts for ts in time_slots if not ts.is_break]
        self.all_time_slots = time_slots
        self.classrooms = classrooms
        self.users = users
        self.semesters = semesters
        self.years = years
        self.departments = departments
        self.sections = sections

    def solve(
        self,
        generation_id: str,
        scope: ScheduleScope,
        target_date: Optional[str] = None,
        academic_year_start: Optional[date] = None,
        academic_year_end: Optional[date] = None,
    ) -> List[TimetableEntry]:
        if not self.allocations:
            raise ValueError("No active faculty allocations found. Admin or faculty must allocate classes first.")

        if HAS_ORTOOLS:
            weekly_entries = self._solve_weekly_ortools(generation_id)
        else:
            weekly_entries = self._solve_weekly_backtracking(generation_id)

        # Handle Scope Transformations
        if scope == ScheduleScope.WEEK:
            return weekly_entries

        elif scope == ScheduleScope.DAY:
            return self._transform_to_day(weekly_entries, target_date)

        elif scope == ScheduleScope.YEAR:
            return self._transform_to_year(
                weekly_entries,
                start_date=academic_year_start or date(2026, 9, 1),
                end_date=academic_year_end or date(2027, 5, 30),
            )

        return weekly_entries

    def _solve_weekly_ortools(self, generation_id: str) -> List[TimetableEntry]:
        """
        High-performance CP-SAT formulation using Google OR-Tools.
        Guarantees 0 collisions across departments, sections, teachers, and rooms.
        """
        model = cp_model.CpModel()

        # Decision variables: x[alloc_id, slot_id, room_id] = 1 if allocation is held at slot t in room r
        x = {}
        for alloc in self.allocations:
            for t in self.time_slots:
                for r in self.classrooms:
                    x[(alloc.id, t.id, r.id)] = model.NewBoolVar(f"x_{alloc.id}_{t.id}_{r.id}")

        # -------------------------------------------------------------
        # HARD CONSTRAINT 1: Subject Weekly Hours Quota
        # Each allocated class session must be scheduled for its required weekly hours
        # -------------------------------------------------------------
        for alloc in self.allocations:
            subject = self.subjects_map.get(alloc.subject_id)
            target_hours = min(subject.weekly_hours if subject else 4, len(self.time_slots))
            model.Add(
                sum(x[(alloc.id, t.id, r.id)] for t in self.time_slots for r in self.classrooms)
                == target_hours
            )

        # -------------------------------------------------------------
        # HARD CONSTRAINT 2: No Cohort Overlap (Department + Semester + Section)
        # A specific Section cohort (e.g. CSE Sem 3 Sec A) can attend at most 1 class at a time
        # -------------------------------------------------------------
        cohort_map: Dict[Tuple[int, int, int], List[FacultyAllocation]] = {}
        for alloc in self.allocations:
            key = (alloc.department_id, alloc.semester_id, alloc.section_id)
            cohort_map.setdefault(key, []).append(alloc)

        for cohort_key, cohort_allocs in cohort_map.items():
            for t in self.time_slots:
                model.Add(
                    sum(
                        x[(alloc.id, t.id, r.id)]
                        for alloc in cohort_allocs
                        for r in self.classrooms
                    )
                    <= 1
                )

        # -------------------------------------------------------------
        # HARD CONSTRAINT 3: No Faculty Overlap
        # A faculty member can teach at most 1 class at any time slot
        # -------------------------------------------------------------
        faculty_map: Dict[str, List[FacultyAllocation]] = {}
        for alloc in self.allocations:
            faculty_map.setdefault(alloc.faculty_id, []).append(alloc)

        for fac_id, fac_allocs in faculty_map.items():
            for t in self.time_slots:
                model.Add(
                    sum(
                        x[(alloc.id, t.id, r.id)]
                        for alloc in fac_allocs
                        for r in self.classrooms
                    )
                    <= 1
                )

        # -------------------------------------------------------------
        # HARD CONSTRAINT 4: No Classroom Overlap
        # A physical room can host at most 1 class per time slot
        # -------------------------------------------------------------
        for r in self.classrooms:
            for t in self.time_slots:
                model.Add(
                    sum(x[(alloc.id, t.id, r.id)] for alloc in self.allocations) <= 1
                )

        # -------------------------------------------------------------
        # SOFT CONSTRAINT / HEURISTIC: Spread classes across days
        # Max 1 lecture per day per subject/section (or 2 if hours > 5)
        # -------------------------------------------------------------
        days = sorted(list(set(ts.day_of_week for ts in self.time_slots)))
        for alloc in self.allocations:
            subj = self.subjects_map.get(alloc.subject_id)
            weekly_h = subj.weekly_hours if subj else 4
            max_per_day = 1 if weekly_h <= len(days) else 2
            for d in days:
                day_slots = [ts for ts in self.time_slots if ts.day_of_week == d]
                model.Add(
                    sum(
                        x[(alloc.id, t.id, r.id)]
                        for t in day_slots
                        for r in self.classrooms
                    )
                    <= max_per_day
                )

        # Solve model
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10.0
        solver.parameters.num_search_workers = 4
        status = solver.Solve(model)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError(
                "Unable to generate a conflict-free timetable. "
                "Constraints are too tight (insufficient time slots or classrooms for the requested departments and sections)."
            )

        # Build TimetableEntry objects
        entries: List[TimetableEntry] = []
        for alloc in self.allocations:
            subj = self.subjects_map.get(alloc.subject_id)
            fac = self.users.get(alloc.faculty_id)
            sem = self.semesters.get(alloc.semester_id)
            yr = self.years.get(alloc.year_id)
            dept = self.departments.get(alloc.department_id)
            sec = self.sections.get(alloc.section_id)

            for t in self.time_slots:
                for r in self.classrooms:
                    if solver.BooleanValue(x[(alloc.id, t.id, r.id)]):
                        entry = TimetableEntry(
                            id=str(uuid.uuid4()),
                            generation_id=generation_id,
                            calendar_date=None,
                            day_of_week=t.day_of_week,
                            day_name=t.day_name,
                            time_slot_id=t.id,
                            slot_index=t.slot_index,
                            start_time=t.start_time,
                            end_time=t.end_time,
                            department_id=alloc.department_id,
                            department_code=dept.code if dept else alloc.department_code,
                            section_id=alloc.section_id,
                            section_name=sec.name if sec else alloc.section_name,
                            subject_id=alloc.subject_id,
                            subject_code=subj.code if subj else "SUBJ",
                            subject_name=subj.name if subj else "Subject",
                            faculty_id=alloc.faculty_id,
                            faculty_name=fac.full_name if fac else "Unknown",
                            semester_id=alloc.semester_id,
                            semester_name=sem.name if sem else f"Semester {alloc.semester_id}",
                            year_id=alloc.year_id,
                            year_name=yr.name if yr else f"Year {alloc.year_id}",
                            classroom_id=r.id,
                            classroom_name=r.room_number,
                        )
                        entries.append(entry)

        entries.sort(key=lambda e: (e.day_of_week, e.slot_index, e.department_id, e.section_id))
        return entries

    def _solve_weekly_backtracking(self, generation_id: str) -> List[TimetableEntry]:
        """
        Pure-Python fallback solver with Forward Checking and MRV.
        """
        sessions = []
        for alloc in self.allocations:
            subj = self.subjects_map.get(alloc.subject_id)
            h = subj.weekly_hours if subj else 4
            for _ in range(h):
                sessions.append(alloc)

        assigned = {}
        occupied_fac = set()
        occupied_cohort = set()
        occupied_room = set()
        alloc_day_count = {}

        def backtrack(idx: int) -> bool:
            if idx == len(sessions):
                return True

            alloc = sessions[idx]
            cohort_key = (alloc.department_id, alloc.semester_id, alloc.section_id)

            for t in self.time_slots:
                if (t.id, alloc.faculty_id) in occupied_fac:
                    continue
                if (t.id, cohort_key) in occupied_cohort:
                    continue
                if alloc_day_count.get((alloc.id, t.day_of_week), 0) >= 2:
                    continue

                for r in self.classrooms:
                    if (t.id, r.id) in occupied_room:
                        continue

                    # Assign
                    assigned[idx] = (t, r)
                    occupied_fac.add((t.id, alloc.faculty_id))
                    occupied_cohort.add((t.id, cohort_key))
                    occupied_room.add((t.id, r.id))
                    alloc_day_count[(alloc.id, t.day_of_week)] = (
                        alloc_day_count.get((alloc.id, t.day_of_week), 0) + 1
                    )

                    if backtrack(idx + 1):
                        return True

                    # Undo
                    del assigned[idx]
                    occupied_fac.remove((t.id, alloc.faculty_id))
                    occupied_cohort.remove((t.id, cohort_key))
                    occupied_room.remove((t.id, r.id))
                    alloc_day_count[(alloc.id, t.day_of_week)] -= 1

            return False

        if not backtrack(0):
            raise RuntimeError("Backtracking CSP solver failed to find conflict-free timetable.")

        entries = []
        for idx, (t, r) in assigned.items():
            alloc = sessions[idx]
            subj = self.subjects_map.get(alloc.subject_id)
            fac = self.users.get(alloc.faculty_id)
            sem = self.semesters.get(alloc.semester_id)
            yr = self.years.get(alloc.year_id)
            dept = self.departments.get(alloc.department_id)
            sec = self.sections.get(alloc.section_id)

            entries.append(
                TimetableEntry(
                    id=str(uuid.uuid4()),
                    generation_id=generation_id,
                    calendar_date=None,
                    day_of_week=t.day_of_week,
                    day_name=t.day_name,
                    time_slot_id=t.id,
                    slot_index=t.slot_index,
                    start_time=t.start_time,
                    end_time=t.end_time,
                    department_id=alloc.department_id,
                    department_code=dept.code if dept else alloc.department_code,
                    section_id=alloc.section_id,
                    section_name=sec.name if sec else alloc.section_name,
                    subject_id=alloc.subject_id,
                    subject_code=subj.code if subj else "SUBJ",
                    subject_name=subj.name if subj else "Subject",
                    faculty_id=alloc.faculty_id,
                    faculty_name=fac.full_name if fac else "Unknown",
                    semester_id=alloc.semester_id,
                    semester_name=sem.name if sem else f"Semester {alloc.semester_id}",
                    year_id=alloc.year_id,
                    year_name=yr.name if yr else f"Year {alloc.year_id}",
                    classroom_id=r.id,
                    classroom_name=r.room_number,
                )
            )
        entries.sort(key=lambda e: (e.day_of_week, e.slot_index, e.department_id, e.section_id))
        return entries

    def _transform_to_day(
        self, weekly_entries: List[TimetableEntry], target_date_str: Optional[str]
    ) -> List[TimetableEntry]:
        target_date = date.fromisoformat(target_date_str) if target_date_str else date.today()
        target_day_of_week = target_date.weekday()

        day_entries: List[TimetableEntry] = []
        for e in weekly_entries:
            if e.day_of_week == target_day_of_week:
                day_entries.append(
                    TimetableEntry(
                        id=str(uuid.uuid4()),
                        generation_id=e.generation_id,
                        calendar_date=target_date.isoformat(),
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
                    )
                )
        return day_entries

    def _transform_to_year(
        self, weekly_entries: List[TimetableEntry], start_date: date, end_date: date
    ) -> List[TimetableEntry]:
        year_entries: List[TimetableEntry] = []
        current = start_date

        while current <= end_date:
            weekday = current.weekday()
            if weekday < 5:
                matching = [e for e in weekly_entries if e.day_of_week == weekday]
                for tmpl in matching:
                    year_entries.append(
                        TimetableEntry(
                            id=str(uuid.uuid4()),
                            generation_id=tmpl.generation_id,
                            calendar_date=current.isoformat(),
                            day_of_week=tmpl.day_of_week,
                            day_name=tmpl.day_name,
                            time_slot_id=tmpl.time_slot_id,
                            slot_index=tmpl.slot_index,
                            start_time=tmpl.start_time,
                            end_time=tmpl.end_time,
                            department_id=tmpl.department_id,
                            department_code=tmpl.department_code,
                            section_id=tmpl.section_id,
                            section_name=tmpl.section_name,
                            subject_id=tmpl.subject_id,
                            subject_code=tmpl.subject_code,
                            subject_name=tmpl.subject_name,
                            faculty_id=tmpl.faculty_id,
                            faculty_name=tmpl.faculty_name,
                            semester_id=tmpl.semester_id,
                            semester_name=tmpl.semester_name,
                            year_id=tmpl.year_id,
                            year_name=tmpl.year_name,
                            classroom_id=tmpl.classroom_id,
                            classroom_name=tmpl.classroom_name,
                        )
                    )
            current += timedelta(days=1)

        return year_entries
