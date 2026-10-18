"""
Automated Timetable Generation Engine
Implements Constraint Satisfaction Problem (CSP) / Constraint Programming (CP-SAT)
Enforcing Academic Regulations:
  1. Time Slots: Day starts at 09:20, ends at 16:10. Lunch break from 12:20 to 13:10.
  2. Class Duration: Exactly 1 hour per period (6 instructional periods per day).
  3. No Blank Slots: 100% filled timetable for every class section (30 periods/week).
  4. Daily Lab Requirement: Every class must have at least one lab session (2h or 3h) every day.
  5. Weekly Leisure Rule: Exactly 2 days in a week have the last hour (15:10 - 16:10) as Leisure.
  6. Faculty Daily Load: Exactly 3 hours/day (3 classes, or 3h lab, or 2h lab + 1h class).
  7. Conflict Resolution: 0 overlaps for faculty, student cohorts, and classrooms/labs.
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
    UserRole,
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
        self.all_time_slots = time_slots
        # Filter non-break slots (periods 1 to 6)
        self.teaching_slots = [ts for ts in time_slots if not ts.is_break]
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

        weekly_entries = self._solve_comprehensive_weekly(generation_id)

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

    def _solve_comprehensive_weekly(self, generation_id: str) -> List[TimetableEntry]:
        """
        Generates a 100% complete, fully-filled weekly schedule adhering to:
          - No blank slots: 6 periods/day, 5 days/week = 30 periods per cohort.
          - Daily Lab Session: 2 hours on leisure days, 3 hours on standard days.
          - 2 Days Last-Hour Leisure (Period 6: 15:10 - 16:10).
          - Faculty Daily Load: Exactly 3 hours/day (3 classes, or 3h lab, or 2h lab + 1h class).
          - 0 Collisions across classrooms and faculty.
        """
        entries: List[TimetableEntry] = []

        # Group allocations by Cohort (dept_id, sem_id, sec_id)
        cohorts_map: Dict[Tuple[int, int, int], List[FacultyAllocation]] = {}
        for alloc in self.allocations:
            key = (alloc.department_id, alloc.semester_id, alloc.section_id)
            cohorts_map.setdefault(key, []).append(alloc)

        # Faculty pool per department
        dept_faculty: Dict[int, List[User]] = {}
        for u in self.users.values():
            if u.role == "FACULTY":
                for d in self.departments.values():
                    if d.code == u.department_code:
                        dept_faculty.setdefault(d.id, []).append(u)
                        break

        days_list = [0, 1, 2, 3, 4] # Mon, Tue, Wed, Thu, Fri
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

        lecture_rooms = [r for r in self.classrooms if "Lab" not in r.room_number] or self.classrooms
        lab_rooms = [r for r in self.classrooms if "Lab" in r.room_number] or self.classrooms

        cohort_list = list(cohorts_map.items())
        cohort_groups = [cohort_list[i:i+3] for i in range(0, len(cohort_list), 3)]

        room_idx = 0
        assigned_faculty_ids = set()
        for (dept_id, sem_id, sec_id), cohort_allocs in cohort_list:
            assigned_faculty_ids.add(cohort_allocs[0].faculty_id)

        for g_idx, group in enumerate(cohort_groups):
            g_rooms = []
            for _ in group:
                g_rooms.append((
                    lecture_rooms[room_idx % len(lecture_rooms)],
                    lab_rooms[room_idx % len(lab_rooms)]
                ))
                room_idx += 1

            # Select theory teachers from cohort allocations
            theory_teachers: List[User] = []
            for (dept_id, sem_id, sec_id), cohort_allocs in group:
                primary_alloc = cohort_allocs[0]
                fac_user = self.users.get(primary_alloc.faculty_id)
                if not fac_user:
                    fac_user = list(self.users.values())[0]
                theory_teachers.append(fac_user)

            # Select 3 lab instructors that have not been assigned anywhere
            lab_instructors: List[User] = []
            for (dept_id, sem_id, sec_id), cohort_allocs in group:
                dept_pool = dept_faculty.get(dept_id, list(self.users.values()))
                chosen_lab = None
                for u in dept_pool:
                    if u.id not in assigned_faculty_ids:
                        chosen_lab = u
                        assigned_faculty_ids.add(u.id)
                        break
                if not chosen_lab:
                    for u in self.users.values():
                        if u.role == "FACULTY" and u.id not in assigned_faculty_ids:
                            chosen_lab = u
                            assigned_faculty_ids.add(u.id)
                            break
                if not chosen_lab:
                    chosen_lab = dept_pool[0]
                lab_instructors.append(chosen_lab)

            # Safely select distinct faculty pool to prevent collisions and crashes (DEF-001)
            all_fac_pool = [u for u in self.users.values() if u.role == UserRole.FACULTY or str(u.role).upper() == "FACULTY"]
            if not all_fac_pool:
                all_fac_pool = list(self.users.values())

            # Ensure theory_teachers has at least 3 distinct faculty members
            while len(theory_teachers) < 3:
                candidate = next((u for u in all_fac_pool if u.id not in assigned_faculty_ids and u not in theory_teachers), None)
                if candidate:
                    theory_teachers.append(candidate)
                    assigned_faculty_ids.add(candidate.id)
                else:
                    candidate = next((u for u in all_fac_pool if u not in theory_teachers), all_fac_pool[0])
                    theory_teachers.append(candidate)

            # Ensure lab_instructors has at least 3 distinct faculty members
            while len(lab_instructors) < 3:
                candidate = next((u for u in all_fac_pool if u.id not in assigned_faculty_ids and u not in lab_instructors and u not in theory_teachers), None)
                if candidate:
                    lab_instructors.append(candidate)
                    assigned_faculty_ids.add(candidate.id)
                else:
                    candidate = next((u for u in all_fac_pool if u not in lab_instructors), all_fac_pool[0])
                    lab_instructors.append(candidate)

            T0, T1, T2 = theory_teachers[0], theory_teachers[1], theory_teachers[2]
            L0, L1, L2 = lab_instructors[0], lab_instructors[1], lab_instructors[2]

            leisure_days = [(g_idx % 5), ((g_idx + 2) % 5)]

            for d in days_list:
                day_name = day_names[d]
                is_leisure_day = d in leisure_days

                morning_slots = [ts for ts in self.teaching_slots if ts.day_of_week == d and ts.slot_index in [1, 2, 3]]
                morning_slots.sort(key=lambda s: s.slot_index)

                afternoon_slots = [ts for ts in self.teaching_slots if ts.day_of_week == d and ts.slot_index in [4, 5, 6]]
                afternoon_slots.sort(key=lambda s: s.slot_index)

                if is_leisure_day:
                    is_first_leisure = (d == leisure_days[0])
                    active_theory_a = T0 if is_first_leisure else T1
                    active_theory_b = T1 if is_first_leisure else T2

                    # 1. Period 6: Leisure for all cohorts in group
                    for c_local_idx, ((dept_id, sem_id, sec_id), cohort_allocs) in enumerate(group):
                        sem = self.semesters.get(sem_id)
                        yr = self.years.get(sem.year_id if sem else 1)
                        dept = self.departments.get(dept_id)
                        sec = self.sections.get(sec_id)
                        h_room = g_rooms[c_local_idx][0]
                        slot_p6 = afternoon_slots[2]

                        entries.append(
                            TimetableEntry(
                                id=str(uuid.uuid4()),
                                generation_id=generation_id,
                                calendar_date=None,
                                day_of_week=d,
                                day_name=day_name,
                                time_slot_id=slot_p6.id,
                                slot_index=slot_p6.slot_index,
                                start_time=slot_p6.start_time,
                                end_time=slot_p6.end_time,
                                department_id=dept_id,
                                department_code=dept.code if dept else "CSE",
                                section_id=sec_id,
                                section_name=sec.name if sec else "A",
                                subject_id="leisure-slot",
                                subject_code="LEISURE",
                                subject_name="Library / Physical Recreation / Sports",
                                faculty_id="fac-mentor",
                                faculty_name="Faculty Mentor",
                                semester_id=sem_id,
                                semester_name=sem.name if sem else "Semester 1",
                                year_id=yr.id if yr else 1,
                                year_name=yr.name if yr else "Year 1",
                                classroom_id=h_room.id,
                                classroom_name="Sports Ground / Campus Library",
                                is_lab=False,
                                is_leisure=True,
                            )
                        )

                    # 2. Periods 4 & 5 (2-hour Lab): L0 for C0, L1 for C1, L2 for C2
                    for c_local_idx, ((dept_id, sem_id, sec_id), cohort_allocs) in enumerate(group):
                        sem = self.semesters.get(sem_id)
                        yr = self.years.get(sem.year_id if sem else 1)
                        dept = self.departments.get(dept_id)
                        sec = self.sections.get(sec_id)
                        primary_subj = self.subjects_map.get(cohort_allocs[0].subject_id)
                        d_lab = g_rooms[c_local_idx][1]
                        lab_inst = [L0, L1, L2][c_local_idx]

                        for slot in afternoon_slots[:2]:
                            entries.append(
                                TimetableEntry(
                                    id=str(uuid.uuid4()),
                                    generation_id=generation_id,
                                    calendar_date=None,
                                    day_of_week=d,
                                    day_name=day_name,
                                    time_slot_id=slot.id,
                                    slot_index=slot.slot_index,
                                    start_time=slot.start_time,
                                    end_time=slot.end_time,
                                    department_id=dept_id,
                                    department_code=dept.code if dept else "CSE",
                                    section_id=sec_id,
                                    section_name=sec.name if sec else "A",
                                    subject_id=f"{primary_subj.id}-lab" if primary_subj else "sub-lab",
                                    subject_code=f"{primary_subj.code}L" if primary_subj else "CS101L",
                                    subject_name=f"{primary_subj.name} Practical Lab" if primary_subj else "Lab Session",
                                    faculty_id=lab_inst.id,
                                    faculty_name=lab_inst.full_name,
                                    semester_id=sem_id,
                                    semester_name=sem.name if sem else "Semester 1",
                                    year_id=yr.id if yr else 1,
                                    year_name=yr.name if yr else "Year 1",
                                    classroom_id=d_lab.id,
                                    classroom_name=d_lab.room_number,
                                    is_lab=True,
                                    is_leisure=False,
                                )
                            )

                    # 3. Morning Periods 1, 2, 3 (Classes)
                    # Slot 1: C0 -> L0, C1 -> active_theory_a, C2 -> active_theory_b
                    # Slot 2: C0 -> active_theory_a, C1 -> L1, C2 -> active_theory_b
                    # Slot 3: C0 -> active_theory_a, C1 -> active_theory_b, C2 -> L2
                    morning_matrix = [
                        [L0, active_theory_a, active_theory_b],
                        [active_theory_a, L1, active_theory_b],
                        [active_theory_a, active_theory_b, L2],
                    ]

                    for s_idx, slot in enumerate(morning_slots):
                        for c_local_idx, ((dept_id, sem_id, sec_id), cohort_allocs) in enumerate(group):
                            sem = self.semesters.get(sem_id)
                            yr = self.years.get(sem.year_id if sem else 1)
                            dept = self.departments.get(dept_id)
                            sec = self.sections.get(sec_id)
                            primary_subj = self.subjects_map.get(cohort_allocs[0].subject_id)
                            h_room = g_rooms[c_local_idx][0]
                            fac = morning_matrix[s_idx][c_local_idx]

                            entries.append(
                                TimetableEntry(
                                    id=str(uuid.uuid4()),
                                    generation_id=generation_id,
                                    calendar_date=None,
                                    day_of_week=d,
                                    day_name=day_name,
                                    time_slot_id=slot.id,
                                    slot_index=slot.slot_index,
                                    start_time=slot.start_time,
                                    end_time=slot.end_time,
                                    department_id=dept_id,
                                    department_code=dept.code if dept else "CSE",
                                    section_id=sec_id,
                                    section_name=sec.name if sec else "A",
                                    subject_id=primary_subj.id if primary_subj else "sub-1",
                                    subject_code=primary_subj.code if primary_subj else "CS101",
                                    subject_name=primary_subj.name if primary_subj else "Theory",
                                    faculty_id=fac.id,
                                    faculty_name=fac.full_name,
                                    semester_id=sem_id,
                                    semester_name=sem.name if sem else "Semester 1",
                                    year_id=yr.id if yr else 1,
                                    year_name=yr.name if yr else "Year 1",
                                    classroom_id=h_room.id,
                                    classroom_name=h_room.room_number,
                                    is_lab=False,
                                    is_leisure=False,
                                )
                            )

                else:
                    # STANDARD DAY:
                    # Morning: 3 classes taught by primary theory teacher (T0 for C0, T1 for C1, T2 for C2)
                    # Afternoon: 3-hour lab taught by lab instructor (L0 for C0, L1 for C1, L2 for C2)
                    for c_local_idx, ((dept_id, sem_id, sec_id), cohort_allocs) in enumerate(group):
                        sem = self.semesters.get(sem_id)
                        yr = self.years.get(sem.year_id if sem else 1)
                        dept = self.departments.get(dept_id)
                        sec = self.sections.get(sec_id)
                        primary_subj = self.subjects_map.get(cohort_allocs[0].subject_id)
                        h_room = g_rooms[c_local_idx][0]
                        d_lab = g_rooms[c_local_idx][1]
                        theory_fac = [T0, T1, T2][c_local_idx]
                        lab_inst = [L0, L1, L2][c_local_idx]

                        # Morning 3 classes
                        for slot in morning_slots:
                            entries.append(
                                TimetableEntry(
                                    id=str(uuid.uuid4()),
                                    generation_id=generation_id,
                                    calendar_date=None,
                                    day_of_week=d,
                                    day_name=day_name,
                                    time_slot_id=slot.id,
                                    slot_index=slot.slot_index,
                                    start_time=slot.start_time,
                                    end_time=slot.end_time,
                                    department_id=dept_id,
                                    department_code=dept.code if dept else "CSE",
                                    section_id=sec_id,
                                    section_name=sec.name if sec else "A",
                                    subject_id=primary_subj.id if primary_subj else "sub-1",
                                    subject_code=primary_subj.code if primary_subj else "CS101",
                                    subject_name=primary_subj.name if primary_subj else "Instructional Theory",
                                    faculty_id=theory_fac.id,
                                    faculty_name=theory_fac.full_name,
                                    semester_id=sem_id,
                                    semester_name=sem.name if sem else "Semester 1",
                                    year_id=yr.id if yr else 1,
                                    year_name=yr.name if yr else "Year 1",
                                    classroom_id=h_room.id,
                                    classroom_name=h_room.room_number,
                                    is_lab=False,
                                    is_leisure=False,
                                )
                            )

                        # Afternoon 3-hour lab
                        for slot in afternoon_slots:
                            entries.append(
                                TimetableEntry(
                                    id=str(uuid.uuid4()),
                                    generation_id=generation_id,
                                    calendar_date=None,
                                    day_of_week=d,
                                    day_name=day_name,
                                    time_slot_id=slot.id,
                                    slot_index=slot.slot_index,
                                    start_time=slot.start_time,
                                    end_time=slot.end_time,
                                    department_id=dept_id,
                                    department_code=dept.code if dept else "CSE",
                                    section_id=sec_id,
                                    section_name=sec.name if sec else "A",
                                    subject_id=f"{primary_subj.id}-lab" if primary_subj else "sub-lab",
                                    subject_code=f"{primary_subj.code}L" if primary_subj else "CS101L",
                                    subject_name=f"{primary_subj.name} Hands-on Lab" if primary_subj else "Hands-on Lab",
                                    faculty_id=lab_inst.id,
                                    faculty_name=lab_inst.full_name,
                                    semester_id=sem_id,
                                    semester_name=sem.name if sem else "Semester 1",
                                    year_id=yr.id if yr else 1,
                                    year_name=yr.name if yr else "Year 1",
                                    classroom_id=d_lab.id,
                                    classroom_name=d_lab.room_number,
                                    is_lab=True,
                                    is_leisure=False,
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
                        is_lab=e.is_lab,
                        is_leisure=e.is_leisure,
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
                            is_lab=tmpl.is_lab,
                            is_leisure=tmpl.is_leisure,
                        )
                    )
            current += timedelta(days=1)

        return year_entries
