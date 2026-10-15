"""
In-memory relational data store with strict constraint validation.
Emulates the PostgreSQL relational tables with multi-department (CSE, ECE, EEE, MECH)
and 6-section (A through F) structure, enforcing the 1:1 faculty-subject constraint.
Pre-populated with rich mock academic data for immediate out-of-the-box execution.
"""

from typing import Dict, List, Optional
from datetime import date, datetime, timezone
import uuid

from app.models import (
    User,
    UserRole,
    Department,
    Section,
    AcademicYear,
    Year,
    Semester,
    Subject,
    FacultyAllocation,
    TimeSlot,
    Classroom,
    TimetableGeneration,
    ScheduleScope,
    ScheduleStatus,
)

class DataStore:
    def __init__(self):
        self.departments: Dict[int, Department] = {}
        self.sections: Dict[int, Section] = {}
        self.users: Dict[str, User] = {}
        self.academic_years: Dict[int, AcademicYear] = {}
        self.years: Dict[int, Year] = {}
        self.semesters: Dict[int, Semester] = {}
        self.subjects: Dict[str, Subject] = {}
        self.allocations: Dict[str, FacultyAllocation] = {} # key: allocation_id
        self.faculty_allocation_map: Dict[str, str] = {}    # key: faculty_id -> allocation_id (Strict 1:1)
        self.time_slots: Dict[int, TimeSlot] = {}
        self.classrooms: Dict[int, Classroom] = {}
        self.generations: Dict[str, TimetableGeneration] = {}

        self._seed_initial_data()

    def _seed_initial_data(self):
        # 1. Departments (CSE, ECE, EEE, MECH)
        dept_list = [
            Department(id=1, code="CSE", name="Computer Science & Engineering"),
            Department(id=2, code="ECE", name="Electronics & Communication Engineering"),
            Department(id=3, code="EEE", name="Electrical & Electronics Engineering"),
            Department(id=4, code="MECH", name="Mechanical Engineering"),
        ]
        for d in dept_list:
            self.departments[d.id] = d

        # 2. 6 Sections: Section A through Section F
        sec_names = ["A", "B", "C", "D", "E", "F"]
        for idx, name in enumerate(sec_names, start=1):
            self.sections[idx] = Section(id=idx, name=name)

        # 3. Academic Year
        self.academic_years[1] = AcademicYear(
            id=1,
            name="2026-2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 30),
            is_current=True,
        )

        # 4. Years (Freshman to Senior)
        self.years[1] = Year(id=1, name="Year 1 (Freshman)", academic_level=1)
        self.years[2] = Year(id=2, name="Year 2 (Sophomore)", academic_level=2)
        self.years[3] = Year(id=3, name="Year 3 (Junior)", academic_level=3)
        self.years[4] = Year(id=4, name="Year 4 (Senior)", academic_level=4)

        # 5. Semesters
        self.semesters[1] = Semester(id=1, year_id=1, name="Semester 1", term_number=1)
        self.semesters[3] = Semester(id=3, year_id=2, name="Semester 3", term_number=3)
        self.semesters[5] = Semester(id=5, year_id=3, name="Semester 5", term_number=5)
        self.semesters[7] = Semester(id=7, year_id=4, name="Semester 7", term_number=7)

        # 6. Users (Admin + Faculty across CSE, ECE, EEE, MECH)
        admin_id = "u-admin-001"
        self.users[admin_id] = User(
            id=admin_id,
            email="admin@university.edu",
            password="admin123",
            full_name="Dr. Alan Turing (Dean/Admin)",
            role=UserRole.ADMIN,
            department="Academic Affairs",
            department_code="ALL",
        )

        faculty_data = [
            # CSE Faculty
            ("fac-cse-01", "grace.hopper@univ.edu", "Dr. Grace Hopper", "Computer Science & Engineering", "CSE", "faculty123"),
            ("fac-cse-02", "donald.knuth@univ.edu", "Prof. Donald Knuth", "Computer Science & Engineering", "CSE", "faculty123"),
            ("fac-cse-03", "barbara.liskov@univ.edu", "Dr. Barbara Liskov", "Computer Science & Engineering", "CSE", "faculty123"),
            # ECE Faculty
            ("fac-ece-01", "claude.shannon@univ.edu", "Dr. Claude Shannon", "Electronics & Communication", "ECE", "faculty123"),
            ("fac-ece-02", "heinrich.hertz@univ.edu", "Prof. Heinrich Hertz", "Electronics & Communication", "ECE", "faculty123"),
            # EEE Faculty
            ("fac-eee-01", "nikola.tesla@univ.edu", "Dr. Nikola Tesla", "Electrical & Electronics", "EEE", "faculty123"),
            ("fac-eee-02", "michael.faraday@univ.edu", "Prof. Michael Faraday", "Electrical & Electronics", "EEE", "faculty123"),
            # MECH Faculty
            ("fac-mech-01", "james.watt@univ.edu", "Dr. James Watt", "Mechanical Engineering", "MECH", "faculty123"),
            ("fac-mech-02", "rudolf.diesel@univ.edu", "Prof. Rudolf Diesel", "Mechanical Engineering", "MECH", "faculty123"),
        ]

        for uid, email, name, dept, dept_code, pwd in faculty_data:
            self.users[uid] = User(
                id=uid,
                email=email,
                password=pwd,
                full_name=name,
                role=UserRole.FACULTY,
                department=dept,
                department_code=dept_code,
            )

        # 7. Subjects across Departments & Semesters
        subjects_data = [
            # CSE
            Subject(id="sub-cs-101", code="CS101", name="Intro to Computing", department_id=1, department_code="CSE", semester_id=1, weekly_hours=3),
            Subject(id="sub-cs-201", code="CS201", name="Data Structures & Algorithms", department_id=1, department_code="CSE", semester_id=3, weekly_hours=4),
            Subject(id="sub-cs-301", code="CS301", name="Database Management Systems", department_id=1, department_code="CSE", semester_id=5, weekly_hours=4),
            Subject(id="sub-cs-401", code="CS401", name="Artificial Intelligence", department_id=1, department_code="CSE", semester_id=7, weekly_hours=3),
            
            # ECE
            Subject(id="sub-ec-101", code="EC101", name="Basic Electronics", department_id=2, department_code="ECE", semester_id=1, weekly_hours=3),
            Subject(id="sub-ec-201", code="EC201", name="Signals & Systems", department_id=2, department_code="ECE", semester_id=3, weekly_hours=4),
            Subject(id="sub-ec-301", code="EC301", name="Digital Signal Processing", department_id=2, department_code="ECE", semester_id=5, weekly_hours=4),
            Subject(id="sub-ec-401", code="EC401", name="VLSI Circuit Design", department_id=2, department_code="ECE", semester_id=7, weekly_hours=3),
            
            # EEE
            Subject(id="sub-ee-101", code="EE101", name="Circuit Theory & Networks", department_id=3, department_code="EEE", semester_id=1, weekly_hours=3),
            Subject(id="sub-ee-201", code="EE201", name="Electrical Machines", department_id=3, department_code="EEE", semester_id=3, weekly_hours=4),
            Subject(id="sub-ee-301", code="EE301", name="Power Systems & Grid", department_id=3, department_code="EEE", semester_id=5, weekly_hours=4),
            Subject(id="sub-ee-401", code="EE401", name="Control Engineering", department_id=3, department_code="EEE", semester_id=7, weekly_hours=3),

            # MECH
            Subject(id="sub-me-101", code="ME101", name="Engineering Mechanics", department_id=4, department_code="MECH", semester_id=1, weekly_hours=3),
            Subject(id="sub-me-201", code="ME201", name="Engineering Thermodynamics", department_id=4, department_code="MECH", semester_id=3, weekly_hours=4),
            Subject(id="sub-me-301", code="ME301", name="Fluid Dynamics & Machinery", department_id=4, department_code="MECH", semester_id=5, weekly_hours=4),
            Subject(id="sub-me-401", code="ME401", name="Robotics & Industrial Automation", department_id=4, department_code="MECH", semester_id=7, weekly_hours=3),
        ]

        for s in subjects_data:
            self.subjects[s.id] = s

        # 8. Classrooms (Expanded for multi-department and multi-section handling)
        rooms = [
            Classroom(id=1, room_number="Hall-101", building="Main Academic Block", capacity=70),
            Classroom(id=2, room_number="Hall-102", building="Main Academic Block", capacity=70),
            Classroom(id=3, room_number="Hall-201", building="Computing Center", capacity=60),
            Classroom(id=4, room_number="Hall-202", building="Computing Center", capacity=60),
            Classroom(id=5, room_number="EC-Lab-A", building="Turing Complex", capacity=60),
            Classroom(id=6, room_number="EE-Lab-B", building="Tesla Pavilion", capacity=60),
            Classroom(id=7, room_number="ME-Lab-C", building="Watt Works", capacity=60),
            Classroom(id=8, room_number="Seminar-Hall", building="Central Library", capacity=120),
        ]
        for r in rooms:
            self.classrooms[r.id] = r

        # 9. Time Slots (Monday - Friday, 6 slots per day: 09:00 to 15:00, with slot 4 as Lunch Break)
        days = [(0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"), (4, "Friday")]
        slot_times = [
            (1, "09:00", "10:00", False),
            (2, "10:00", "11:00", False),
            (3, "11:00", "12:00", False),
            (4, "12:00", "13:00", True),  # Campus Lunch & Recess Break
            (5, "13:00", "14:00", False),
            (6, "14:00", "15:00", False),
        ]

        ts_id = 1
        for day_idx, day_name in days:
            for s_idx, start_t, end_t, is_break in slot_times:
                self.time_slots[ts_id] = TimeSlot(
                    id=ts_id,
                    day_of_week=day_idx,
                    day_name=day_name,
                    slot_index=s_idx,
                    start_time=start_t,
                    end_time=end_t,
                    is_break=is_break,
                )
                ts_id += 1

        # 10. Initial Allocations (Admin-assigned across departments and 6 sections: A, B, C, D, E, F)
        initial_allocs = [
            # CSE Faculty -> Section A & B
            ("fac-cse-01", "sub-cs-101", 1, 1, 1, 1), # Grace Hopper -> CS101, CSE, Yr 1, Sem 1, Sec A
            ("fac-cse-02", "sub-cs-201", 1, 2, 3, 2), # Donald Knuth -> CS201, CSE, Yr 2, Sem 3, Sec B
            ("fac-cse-03", "sub-cs-301", 1, 3, 5, 1), # Barbara Liskov -> CS301, CSE, Yr 3, Sem 5, Sec A

            # ECE Faculty -> Section C & D
            ("fac-ece-01", "sub-ec-201", 2, 2, 3, 3), # Claude Shannon -> EC201, ECE, Yr 2, Sem 3, Sec C
            ("fac-ece-02", "sub-ec-101", 2, 1, 1, 4), # Heinrich Hertz -> EC101, ECE, Yr 1, Sem 1, Sec D

            # EEE Faculty -> Section D & E
            ("fac-eee-01", "sub-ee-201", 3, 2, 3, 4), # Nikola Tesla -> EE201, EEE, Yr 2, Sem 3, Sec D
            ("fac-eee-02", "sub-ee-101", 3, 1, 1, 5), # Michael Faraday -> EE101, EEE, Yr 1, Sem 1, Sec E

            # MECH Faculty -> Section E & F
            ("fac-mech-01", "sub-me-201", 4, 2, 3, 5), # James Watt -> ME201, MECH, Yr 2, Sem 3, Sec E
            ("fac-mech-02", "sub-me-101", 4, 1, 1, 6), # Rudolf Diesel -> ME101, MECH, Yr 1, Sem 1, Sec F
        ]

        for f_id, s_id, d_id, y_id, sem_id, sec_id in initial_allocs:
            self.allocate_faculty_subject(
                faculty_id=f_id,
                subject_id=s_id,
                department_id=d_id,
                year_id=y_id,
                semester_id=sem_id,
                section_id=sec_id,
                allocated_by="ADMIN",
            )

    def allocate_faculty_subject(
        self,
        faculty_id: str,
        subject_id: str,
        department_id: int,
        year_id: int,
        semester_id: int,
        section_id: int,
        academic_year_id: int = 1,
        allocated_by: str = "ADMIN",
    ) -> FacultyAllocation:
        """
        Enforces the Crucial Constraint:
        Each faculty member is restricted to choosing/being allocated ONLY ONE subject.
        Admin has authority to assign the faculty to specific Department, Year, Semester, and Section (A-F).
        If an allocation already exists for this faculty member, it replaces or updates it.
        """
        if faculty_id not in self.users:
            raise ValueError(f"Faculty member {faculty_id} not found.")

        user = self.users[faculty_id]
        if user.role != UserRole.FACULTY:
            raise ValueError(f"User {user.full_name} is not a faculty member.")

        if subject_id not in self.subjects:
            raise ValueError(f"Subject {subject_id} not found.")

        subject = self.subjects[subject_id]
        if subject.semester_id != semester_id:
            raise ValueError(
                f"Subject '{subject.name}' ({subject.code}) belongs to Semester {subject.semester_id}, "
                f"not requested Semester {semester_id}."
            )

        if department_id not in self.departments:
            raise ValueError(f"Department ID {department_id} not found.")

        dept = self.departments[department_id]
        if subject.department_id != department_id:
            raise ValueError(
                f"Subject '{subject.name}' belongs to department {subject.department_code}, "
                f"not requested department {dept.code}."
            )

        if semester_id not in self.semesters:
            raise ValueError(f"Semester {semester_id} not found.")

        semester = self.semesters[semester_id]
        if semester.year_id != year_id:
            raise ValueError(
                f"Semester {semester.name} belongs to Year {semester.year_id}, "
                f"not specified Year {year_id}."
            )

        if section_id not in self.sections:
            raise ValueError(f"Section ID {section_id} not found. Must be between 1 and 6 (Sections A-F).")

        sec = self.sections[section_id]

        # Enforce 1:1 per faculty: If an allocation exists for this faculty, replace it
        if faculty_id in self.faculty_allocation_map:
            existing_alloc_id = self.faculty_allocation_map[faculty_id]
            alloc = self.allocations[existing_alloc_id]
            alloc.subject_id = subject_id
            alloc.department_id = department_id
            alloc.department_code = dept.code
            alloc.year_id = year_id
            alloc.semester_id = semester_id
            alloc.section_id = section_id
            alloc.section_name = sec.name
            alloc.academic_year_id = academic_year_id
            alloc.allocated_by = allocated_by
            alloc.created_at = datetime.now(timezone.utc)
            return alloc

        alloc_id = f"alloc-{uuid.uuid4().hex[:8]}"
        alloc = FacultyAllocation(
            id=alloc_id,
            faculty_id=faculty_id,
            subject_id=subject_id,
            department_id=department_id,
            department_code=dept.code,
            year_id=year_id,
            semester_id=semester_id,
            section_id=section_id,
            section_name=sec.name,
            academic_year_id=academic_year_id,
            allocated_by=allocated_by,
        )
        self.allocations[alloc_id] = alloc
        self.faculty_allocation_map[faculty_id] = alloc_id
        return alloc

# Singleton instance
db = DataStore()
