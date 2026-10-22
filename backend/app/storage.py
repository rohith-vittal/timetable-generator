"""
In-memory & disk-persisted relational data store with strict constraint validation.
Emulates the PostgreSQL relational tables with multi-department (CSE, ECE, EEE, MECH)
and 6-section (A through F) structure, enforcing the 1:1 faculty-subject constraint.
Pre-populated with rich mock academic data for immediate out-of-the-box execution.
"""

from typing import Dict, List, Optional
from datetime import date, datetime, timezone
from dataclasses import asdict
import uuid
import hashlib
import json
import os
from pathlib import Path

def to_dict(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    elif hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    elif isinstance(obj, dict):
        return obj
    return str(obj)

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

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PERSISTENCE_FILE = DATA_DIR / "timetable_store.json"

def hash_password(password: str) -> str:
    """NIST-compliant PBKDF2-HMAC-SHA256 password hashing."""
    salt = b"chronoscheduler_enterprise_salt_2026"
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return f"pbkdf2:{h.hex()}"

def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Verifies plain password against hashed or legacy password."""
    if not stored_hash:
        return False
    if not stored_hash.startswith("pbkdf2:"):
        return plain_password == stored_hash
    return hash_password(plain_password) == stored_hash

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
        self.active_sessions: Dict[str, User] = {}          # Bearer token -> User (RBAC)
        self.is_custom_data: bool = False

        self._init_time_slots()
        has_custom = self._load_from_disk()
        if not has_custom:
            self._seed_initial_data()
            self._load_from_disk()

    def _init_time_slots(self):
        """Standard daily instructional schedule: 09:20 - 16:10 with Lunch 12:20 - 13:10."""
        days = [(0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"), (4, "Friday")]
        slot_schedule = [
            (1, "09:20", "10:20", False), # Period 1
            (2, "10:20", "11:20", False), # Period 2
            (3, "11:20", "12:20", False), # Period 3
            (0, "12:20", "13:10", True),  # Campus Lunch Break (12:20 to 13:10)
            (4, "13:10", "14:10", False), # Period 4
            (5, "14:10", "15:10", False), # Period 5
            (6, "15:10", "16:10", False), # Period 6
        ]

        ts_id = 1
        for day_idx, day_name in days:
            for s_idx, start_t, end_t, is_break in slot_schedule:
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

        # 4. Years (4 Academic Years)
        self.years[1] = Year(id=1, name="Year 1 (Freshman)", academic_level=1)
        self.years[2] = Year(id=2, name="Year 2 (Sophomore)", academic_level=2)
        self.years[3] = Year(id=3, name="Year 3 (Junior)", academic_level=3)
        self.years[4] = Year(id=4, name="Year 4 (Senior)", academic_level=4)

        # 5. Semesters: A year has exactly 2 semesters! (8 Semesters total)
        # Year 1 -> Semester 1 & Semester 2
        self.semesters[1] = Semester(id=1, year_id=1, name="Semester 1", term_number=1)
        self.semesters[2] = Semester(id=2, year_id=1, name="Semester 2", term_number=2)
        # Year 2 -> Semester 3 & Semester 4
        self.semesters[3] = Semester(id=3, year_id=2, name="Semester 3", term_number=3)
        self.semesters[4] = Semester(id=4, year_id=2, name="Semester 4", term_number=4)
        # Year 3 -> Semester 5 & Semester 6
        self.semesters[5] = Semester(id=5, year_id=3, name="Semester 5", term_number=5)
        self.semesters[6] = Semester(id=6, year_id=3, name="Semester 6", term_number=6)
        # Year 4 -> Semester 7 & Semester 8
        self.semesters[7] = Semester(id=7, year_id=4, name="Semester 7", term_number=7)
        self.semesters[8] = Semester(id=8, year_id=4, name="Semester 8", term_number=8)

        # 6. Users (Admin + Faculty across CSE, ECE, EEE, MECH)
        admin_id = "u-admin-001"
        self.users[admin_id] = User(
            id=admin_id,
            email="admin@university.edu",
            password=hash_password("admin123"),
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
            ("fac-cse-04", "tim.berners.lee@univ.edu", "Sir Tim Berners-Lee", "Computer Science & Engineering", "CSE", "faculty123"),
            ("fac-cse-05", "linus.torvalds@univ.edu", "Prof. Linus Torvalds", "Computer Science & Engineering", "CSE", "faculty123"),
            ("fac-cse-06", "ada.lovelace@univ.edu", "Dr. Ada Lovelace", "Computer Science & Engineering", "CSE", "faculty123"),
            # ECE Faculty
            ("fac-ece-01", "claude.shannon@univ.edu", "Dr. Claude Shannon", "Electronics & Communication", "ECE", "faculty123"),
            ("fac-ece-02", "heinrich.hertz@univ.edu", "Prof. Heinrich Hertz", "Electronics & Communication", "ECE", "faculty123"),
            ("fac-ece-03", "guglielmo.marconi@univ.edu", "Prof. Guglielmo Marconi", "Electronics & Communication", "ECE", "faculty123"),
            ("fac-ece-04", "edwin.armstrong@univ.edu", "Dr. Edwin Armstrong", "Electronics & Communication", "ECE", "faculty123"),
            ("fac-ece-05", "jack.kilby@univ.edu", "Dr. Jack Kilby", "Electronics & Communication", "ECE", "faculty123"),
            ("fac-ece-06", "robert.noyce@univ.edu", "Prof. Robert Noyce", "Electronics & Communication", "ECE", "faculty123"),
            # EEE Faculty
            ("fac-eee-01", "nikola.tesla@univ.edu", "Dr. Nikola Tesla", "Electrical & Electronics", "EEE", "faculty123"),
            ("fac-eee-02", "michael.faraday@univ.edu", "Prof. Michael Faraday", "Electrical & Electronics", "EEE", "faculty123"),
            ("fac-eee-03", "thomas.edison@univ.edu", "Prof. Thomas Edison", "Electrical & Electronics", "EEE", "faculty123"),
            ("fac-eee-04", "george.westinghouse@univ.edu", "Dr. George Westinghouse", "Electrical & Electronics", "EEE", "faculty123"),
            ("fac-eee-05", "charles.steinmetz@univ.edu", "Dr. Charles Steinmetz", "Electrical & Electronics", "EEE", "faculty123"),
            ("fac-eee-06", "oliver.heaviside@univ.edu", "Prof. Oliver Heaviside", "Electrical & Electronics", "EEE", "faculty123"),
            # MECH Faculty
            ("fac-mech-01", "james.watt@univ.edu", "Dr. James Watt", "Mechanical Engineering", "MECH", "faculty123"),
            ("fac-mech-02", "rudolf.diesel@univ.edu", "Prof. Rudolf Diesel", "Mechanical Engineering", "MECH", "faculty123"),
            ("fac-mech-03", "henry.ford@univ.edu", "Prof. Henry Ford", "Mechanical Engineering", "MECH", "faculty123"),
            ("fac-mech-04", "karl.benz@univ.edu", "Dr. Karl Benz", "Mechanical Engineering", "MECH", "faculty123"),
            ("fac-mech-05", "nikolaus.otto@univ.edu", "Dr. Nikolaus Otto", "Mechanical Engineering", "MECH", "faculty123"),
            ("fac-mech-06", "sadi.carnot@univ.edu", "Prof. Sadi Carnot", "Mechanical Engineering", "MECH", "faculty123"),
        ]

        for uid, email, name, dept, dept_code, pwd in faculty_data:
            self.users[uid] = User(
                id=uid,
                email=email,
                password=hash_password(pwd),
                full_name=name,
                role=UserRole.FACULTY,
                department=dept,
                department_code=dept_code,
            )

        # 7. Subjects across Departments & Semesters (Both Theory and Labs)
        subjects_data = [
            # CSE
            Subject(id="sub-cs-101", code="CS101", name="Intro to Computing", department_id=1, department_code="CSE", semester_id=1, weekly_hours=3, is_lab=False),
            Subject(id="sub-cs-101L", code="CS101L", name="Computing Lab", department_id=1, department_code="CSE", semester_id=1, weekly_hours=3, is_lab=True),
            Subject(id="sub-cs-102", code="CS102", name="Object Oriented Programming", department_id=1, department_code="CSE", semester_id=2, weekly_hours=3, is_lab=False),
            Subject(id="sub-cs-201", code="CS201", name="Data Structures & Algorithms", department_id=1, department_code="CSE", semester_id=3, weekly_hours=4, is_lab=False),
            Subject(id="sub-cs-201L", code="CS201L", name="Data Structures Lab", department_id=1, department_code="CSE", semester_id=3, weekly_hours=3, is_lab=True),
            Subject(id="sub-cs-301", code="CS301", name="Database Management Systems", department_id=1, department_code="CSE", semester_id=5, weekly_hours=4, is_lab=False),
            Subject(id="sub-cs-301L", code="CS301L", name="DBMS Lab", department_id=1, department_code="CSE", semester_id=5, weekly_hours=3, is_lab=True),
            Subject(id="sub-cs-401", code="CS401", name="Artificial Intelligence", department_id=1, department_code="CSE", semester_id=7, weekly_hours=3, is_lab=False),
            
            # ECE
            Subject(id="sub-ec-101", code="EC101", name="Basic Electronics", department_id=2, department_code="ECE", semester_id=1, weekly_hours=3, is_lab=False),
            Subject(id="sub-ec-101L", code="EC101L", name="Basic Electronics Lab", department_id=2, department_code="ECE", semester_id=1, weekly_hours=3, is_lab=True),
            Subject(id="sub-ec-201", code="EC201", name="Signals & Systems", department_id=2, department_code="ECE", semester_id=3, weekly_hours=4, is_lab=False),
            Subject(id="sub-ec-201L", code="EC201L", name="Signals & DSP Lab", department_id=2, department_code="ECE", semester_id=3, weekly_hours=3, is_lab=True),
            Subject(id="sub-ec-301", code="EC301", name="Digital Signal Processing", department_id=2, department_code="ECE", semester_id=5, weekly_hours=4, is_lab=False),
            Subject(id="sub-ec-401", code="EC401", name="VLSI Circuit Design", department_id=2, department_code="ECE", semester_id=7, weekly_hours=3, is_lab=False),
            
            # EEE
            Subject(id="sub-ee-101", code="EE101", name="Circuit Theory & Networks", department_id=3, department_code="EEE", semester_id=1, weekly_hours=3, is_lab=False),
            Subject(id="sub-ee-101L", code="EE101L", name="Circuits Lab", department_id=3, department_code="EEE", semester_id=1, weekly_hours=3, is_lab=True),
            Subject(id="sub-ee-201", code="EE201", name="Electrical Machines", department_id=3, department_code="EEE", semester_id=3, weekly_hours=4, is_lab=False),
            Subject(id="sub-ee-201L", code="EE201L", name="Electrical Machines Lab", department_id=3, department_code="EEE", semester_id=3, weekly_hours=3, is_lab=True),
            Subject(id="sub-ee-301", code="EE301", name="Power Systems & Grid", department_id=3, department_code="EEE", semester_id=5, weekly_hours=4, is_lab=False),
            Subject(id="sub-ee-401", code="EE401", name="Control Engineering", department_id=3, department_code="EEE", semester_id=7, weekly_hours=3, is_lab=False),

            # MECH
            Subject(id="sub-me-101", code="ME101", name="Engineering Mechanics", department_id=4, department_code="MECH", semester_id=1, weekly_hours=3, is_lab=False),
            Subject(id="sub-me-101L", code="ME101L", name="Workshop & Mechanics Lab", department_id=4, department_code="MECH", semester_id=1, weekly_hours=3, is_lab=True),
            Subject(id="sub-me-201", code="ME201", name="Engineering Thermodynamics", department_id=4, department_code="MECH", semester_id=3, weekly_hours=4, is_lab=False),
            Subject(id="sub-me-201L", code="ME201L", name="Thermal Engineering Lab", department_id=4, department_code="MECH", semester_id=3, weekly_hours=3, is_lab=True),
            Subject(id="sub-me-301", code="ME301", name="Fluid Dynamics & Machinery", department_id=4, department_code="MECH", semester_id=5, weekly_hours=4, is_lab=False),
            Subject(id="sub-me-401", code="ME401", name="Robotics & Industrial Automation", department_id=4, department_code="MECH", semester_id=7, weekly_hours=3, is_lab=False),
        ]

        for s in subjects_data:
            self.subjects[s.id] = s

        # 8. Classrooms & Specialized Labs (12 Lecture Halls + 12 Labs)
        rooms = [
            Classroom(id=1, room_number="LH-101 (Lecture Hall)", building="Academic Block A", capacity=70),
            Classroom(id=2, room_number="LH-102 (Lecture Hall)", building="Academic Block A", capacity=70),
            Classroom(id=3, room_number="LH-103 (Lecture Hall)", building="Academic Block A", capacity=70),
            Classroom(id=4, room_number="LH-104 (Lecture Hall)", building="Academic Block A", capacity=70),
            Classroom(id=5, room_number="LH-201 (Lecture Hall)", building="Academic Block B", capacity=60),
            Classroom(id=6, room_number="LH-202 (Lecture Hall)", building="Academic Block B", capacity=60),
            Classroom(id=7, room_number="LH-203 (Lecture Hall)", building="Academic Block B", capacity=60),
            Classroom(id=8, room_number="LH-204 (Lecture Hall)", building="Academic Block B", capacity=60),
            Classroom(id=9, room_number="LH-301 (Lecture Hall)", building="Academic Block C", capacity=60),
            Classroom(id=10, room_number="LH-302 (Lecture Hall)", building="Academic Block C", capacity=60),
            Classroom(id=11, room_number="LH-303 (Lecture Hall)", building="Academic Block C", capacity=60),
            Classroom(id=12, room_number="LH-304 (Lecture Hall)", building="Academic Block C", capacity=60),
            Classroom(id=13, room_number="CS-Lab-1 (Software Eng)", building="Computing Center", capacity=60),
            Classroom(id=14, room_number="CS-Lab-2 (Algorithms)", building="Computing Center", capacity=60),
            Classroom(id=15, room_number="CS-Lab-3 (Data & AI)", building="Computing Center", capacity=60),
            Classroom(id=16, room_number="EC-Lab-1 (Signals)", building="Turing Pavilion", capacity=60),
            Classroom(id=17, room_number="EC-Lab-2 (VLSI)", building="Turing Pavilion", capacity=60),
            Classroom(id=18, room_number="EC-Lab-3 (Communications)", building="Turing Pavilion", capacity=60),
            Classroom(id=19, room_number="EE-Lab-1 (Circuits)", building="Tesla Pavilion", capacity=60),
            Classroom(id=20, room_number="EE-Lab-2 (Machines)", building="Tesla Pavilion", capacity=60),
            Classroom(id=21, room_number="EE-Lab-3 (Power & Control)", building="Tesla Pavilion", capacity=60),
            Classroom(id=22, room_number="ME-Lab-1 (Mechanics)", building="Watt Works", capacity=60),
            Classroom(id=23, room_number="ME-Lab-2 (Thermodynamics)", building="Watt Works", capacity=60),
            Classroom(id=24, room_number="ME-Lab-3 (Robotics)", building="Watt Works", capacity=60),
        ]
        for r in rooms:
            self.classrooms[r.id] = r

        # 9. Time Slots (Initialized via self._init_time_slots())
        if not self.time_slots:
            self._init_time_slots()

        # 10. Initial Allocations (Strictly 1:1 per faculty)
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
                save_to_disk=False,
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
        save_to_disk: bool = True,
    ) -> FacultyAllocation:
        """
        Enforces the Crucial Constraint:
        Each faculty member is restricted to choosing/being allocated ONLY ONE subject.
        Admin or faculty can specify Year, Semester, and Section.
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
            if save_to_disk:
                self._save_to_disk()
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
        if save_to_disk:
            self._save_to_disk()
        return alloc

    def register_user(
        self,
        email: str,
        password: str,
        full_name: str,
        role: UserRole,
        department_id: Optional[int] = 1,
    ) -> User:
        """
        Registers a new user (Faculty or Admin) in the database.
        Enforces unique email across all users.
        Hashes password with PBKDF2 (DEF-005) and persists to disk (DEF-003).
        """
        for u in self.users.values():
            if u.email.lower() == email.strip().lower():
                raise ValueError(f"An account with email '{email}' already exists.")

        user_id = f"u-{role.value.lower()}-{uuid.uuid4().hex[:8]}"
        dept_name = "Academic Affairs"
        dept_code = "ALL"

        if role == UserRole.FACULTY and department_id and department_id in self.departments:
            dept = self.departments[department_id]
            dept_name = dept.name
            dept_code = dept.code

        new_user = User(
            id=user_id,
            email=email.strip().lower(),
            password=hash_password(password),
            full_name=full_name.strip(),
            role=role,
            department=dept_name,
            department_code=dept_code,
        )
        self.users[user_id] = new_user
        self._save_to_disk()
        return new_user

    def _save_to_disk(self):
        """Persists mutable entities or complete custom state to disk (DEF-003)."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            if self.is_custom_data:
                payload = {
                    "is_custom_data": True,
                    "departments": {did: to_dict(d) for did, d in self.departments.items()},
                    "sections": {sid: to_dict(s) for sid, s in self.sections.items()},
                    "users": {uid: to_dict(u) for uid, u in self.users.items()},
                    "academic_years": {yid: to_dict(y) for yid, y in self.academic_years.items()},
                    "years": {yid: to_dict(y) for yid, y in self.years.items()},
                    "semesters": {sid: to_dict(s) for sid, s in self.semesters.items()},
                    "subjects": {sid: to_dict(s) for sid, s in self.subjects.items()},
                    "classrooms": {cid: to_dict(c) for cid, c in self.classrooms.items()},
                    "allocations": {aid: to_dict(a) for aid, a in self.allocations.items()},
                    "faculty_allocation_map": self.faculty_allocation_map,
                    "generations": {gid: to_dict(g) for gid, g in self.generations.items()},
                }
            else:
                custom_users = {}
                for uid, u in self.users.items():
                    if uid.startswith("u-faculty-") or (uid.startswith("u-admin-") and uid != "u-admin-001"):
                        custom_users[uid] = to_dict(u)
                
                payload = {
                    "is_custom_data": False,
                    "custom_users": custom_users,
                    "allocations": {aid: to_dict(a) for aid, a in self.allocations.items()},
                    "faculty_allocation_map": self.faculty_allocation_map,
                }
            with open(PERSISTENCE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)
        except Exception as ex:
            print(f"Error persisting data to disk: {ex}")

    def _load_from_disk(self) -> bool:
        """Restores persisted state from disk if available (DEF-003). Returns True if custom data was loaded."""
        try:
            if not PERSISTENCE_FILE.exists():
                return False
            with open(PERSISTENCE_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)

            if payload.get("is_custom_data", False):
                self.is_custom_data = True
                self.departments = {int(k): Department(**v) for k, v in payload.get("departments", {}).items()}
                self.sections = {int(k): Section(**v) for k, v in payload.get("sections", {}).items()}

                users_loaded = {}
                for k, v in payload.get("users", {}).items():
                    if isinstance(v.get("role"), str):
                        v["role"] = UserRole(v["role"])
                    users_loaded[k] = User(**v)
                self.users = users_loaded

                ay_loaded = {}
                for k, v in payload.get("academic_years", {}).items():
                    if isinstance(v.get("start_date"), str):
                        v["start_date"] = date.fromisoformat(v["start_date"])
                    if isinstance(v.get("end_date"), str):
                        v["end_date"] = date.fromisoformat(v["end_date"])
                    ay_loaded[int(k)] = AcademicYear(**v)
                self.academic_years = ay_loaded

                self.years = {int(k): Year(**v) for k, v in payload.get("years", {}).items()}
                self.semesters = {int(k): Semester(**v) for k, v in payload.get("semesters", {}).items()}
                self.subjects = {k: Subject(**v) for k, v in payload.get("subjects", {}).items()}
                self.classrooms = {int(k): Classroom(**v) for k, v in payload.get("classrooms", {}).items()}

                allocs_loaded = {}
                for k, v in payload.get("allocations", {}).items():
                    if isinstance(v.get("created_at"), str):
                        try:
                            v["created_at"] = datetime.fromisoformat(v["created_at"])
                        except Exception:
                            v["created_at"] = datetime.now(timezone.utc)
                    allocs_loaded[k] = FacultyAllocation(**v)
                self.allocations = allocs_loaded
                self.faculty_allocation_map = payload.get("faculty_allocation_map", {})
                return True
            else:
                for uid, udata in payload.get("custom_users", {}).items():
                    if isinstance(udata.get("role"), str):
                        udata["role"] = UserRole(udata["role"])
                    self.users[uid] = User(**udata)
                for aid, adata in payload.get("allocations", {}).items():
                    if isinstance(adata.get("created_at"), str):
                        try:
                            adata["created_at"] = datetime.fromisoformat(adata["created_at"])
                        except Exception:
                            adata["created_at"] = datetime.now(timezone.utc)
                    self.allocations[aid] = FacultyAllocation(**adata)
                self.faculty_allocation_map.update(payload.get("faculty_allocation_map", {}))
                return False
        except Exception as ex:
            print(f"Error loading data from disk: {ex}")
            return False

    def clear_mock_data(self, preserve_admin: bool = True) -> Dict[str, Any]:
        """
        Clears all fake/mock entities:
        - Purges 24 mock faculty members
        - Purges 24 mock subjects
        - Purges 24 mock classrooms
        - Purges all mock allocations and timetable generations
        - Preserves the Admin account (so you remain authenticated) and standard schedule structure.
        """
        admin_users = {uid: u for uid, u in self.users.items() if u.role == UserRole.ADMIN}
        if not admin_users and preserve_admin:
            admin_id = "u-admin-001"
            admin_users[admin_id] = User(
                id=admin_id,
                email="admin@university.edu",
                password=hash_password("admin123"),
                full_name="Dr. Alan Turing (Dean/Admin)",
                role=UserRole.ADMIN,
                department="Academic Affairs",
                department_code="ALL",
            )

        self.users = admin_users
        self.subjects = {}
        self.classrooms = {}
        self.allocations = {}
        self.faculty_allocation_map = {}
        self.generations = {}
        self.is_custom_data = True

        self._save_to_disk()
        return {
            "status": "success",
            "message": "All mock data (faculty, subjects, classrooms, allocations, timetables) cleared successfully. Ready for original institutional data.",
            "is_custom_data": True,
            "remaining_users": [u.email for u in self.users.values()],
        }

    def reset_to_demo_data(self) -> Dict[str, Any]:
        """Restores the complete out-of-the-box demo/mock dataset."""
        self.departments.clear()
        self.sections.clear()
        self.users.clear()
        self.academic_years.clear()
        self.years.clear()
        self.semesters.clear()
        self.subjects.clear()
        self.classrooms.clear()
        self.allocations.clear()
        self.faculty_allocation_map.clear()
        self.generations.clear()
        self.is_custom_data = False

        self._seed_initial_data()
        self._save_to_disk()
        return {
            "status": "success",
            "message": "Demo data restored successfully.",
            "total_faculty": len([u for u in self.users.values() if u.role == UserRole.FACULTY]),
            "total_subjects": len(self.subjects),
            "total_classrooms": len(self.classrooms),
            "total_allocations": len(self.allocations),
        }

    def import_institutional_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Imports and validates real institutional data:
        - Departments (optional or replaces)
        - Sections (default A-F if not provided)
        - Faculty list (hashes passwords, links to departments)
        - Subjects list (theory and labs, links to departments and semesters)
        - Classrooms list (lecture halls and labs)
        - Allocations (optional initial subject allocations, strictly 1:1 per faculty)
        """
        if data.get("clear_existing_mock_data", True):
            self.clear_mock_data(preserve_admin=True)

        if data.get("admin_email") and data.get("admin_password"):
            admin_id = "u-admin-001"
            self.users[admin_id] = User(
                id=admin_id,
                email=data["admin_email"].strip().lower(),
                password=hash_password(data["admin_password"]),
                full_name=data.get("admin_name", "Institution Administrator"),
                role=UserRole.ADMIN,
                department="Academic Affairs",
                department_code="ALL",
            )

        if data.get("departments"):
            self.departments.clear()
            for idx, d in enumerate(data["departments"], start=1):
                code = d["code"].strip().upper()
                name = d.get("name", code)
                self.departments[idx] = Department(id=idx, code=code, name=name)

        if data.get("classrooms"):
            self.classrooms.clear()
            for idx, c in enumerate(data["classrooms"], start=1):
                self.classrooms[idx] = Classroom(
                    id=idx,
                    room_number=c["room_number"].strip(),
                    building=c.get("building", "Academic Block"),
                    capacity=int(c.get("capacity", 60)),
                )
        elif not self.classrooms:
            for idx in range(1, 13):
                self.classrooms[idx] = Classroom(id=idx, room_number=f"LH-{100+idx} (Lecture Hall)", building="Academic Block A", capacity=70)
            for idx in range(13, 25):
                self.classrooms[idx] = Classroom(id=idx, room_number=f"Lab-{idx-12} (Practical Lab)", building="Computing & Tech Center", capacity=60)

        email_to_faculty = {}
        for idx, f in enumerate(data.get("faculty", []), start=1):
            email = f["email"].strip().lower()
            name = f["full_name"].strip()
            dept_code = f.get("department_code", "CSE").strip().upper()
            pwd = f.get("password", "faculty123")
            
            dept_obj = next((d for d in self.departments.values() if d.code == dept_code), None)
            dept_name = dept_obj.name if dept_obj else dept_code

            fac_id = f"fac-real-{idx:03d}"
            u = User(
                id=fac_id,
                email=email,
                password=hash_password(pwd),
                full_name=name,
                role=UserRole.FACULTY,
                department=dept_name,
                department_code=dept_code,
            )
            self.users[fac_id] = u
            email_to_faculty[email] = u

        code_to_subject = {}
        for idx, s in enumerate(data.get("subjects", []), start=1):
            s_code = s["code"].strip().upper()
            s_name = s["name"].strip()
            dept_code = s.get("department_code", "CSE").strip().upper()
            sem_id = int(s.get("semester_id", 1))
            is_lab = bool(s.get("is_lab", False) or "lab" in s_name.lower() or s_code.endswith("L"))
            weekly_hours = int(s.get("weekly_hours", 3))

            dept_obj = next((d for d in self.departments.values() if d.code == dept_code), None)
            dept_id = dept_obj.id if dept_obj else 1

            sub_id = f"sub-real-{idx:03d}"
            sub = Subject(
                id=sub_id,
                code=s_code,
                name=s_name,
                department_id=dept_id,
                department_code=dept_code,
                semester_id=sem_id,
                weekly_hours=weekly_hours,
                is_lab=is_lab,
            )
            self.subjects[sub_id] = sub
            code_to_subject[s_code] = sub

        imported_allocations = 0
        if data.get("allocations"):
            for alloc_in in data["allocations"]:
                f_email = alloc_in["faculty_email"].strip().lower()
                s_code = alloc_in["subject_code"].strip().upper()
                sec_name = alloc_in.get("section_name", "A").strip().upper()

                faculty = email_to_faculty.get(f_email)
                subject = code_to_subject.get(s_code)
                sec_obj = next((sec for sec in self.sections.values() if sec.name == sec_name), self.sections[1])

                if faculty and subject:
                    sem_id = subject.semester_id
                    sem_obj = self.semesters.get(sem_id)
                    yr_id = sem_obj.year_id if sem_obj else 1

                    self.allocate_faculty_subject(
                        faculty_id=faculty.id,
                        subject_id=subject.id,
                        department_id=subject.department_id,
                        year_id=yr_id,
                        semester_id=sem_id,
                        section_id=sec_obj.id,
                        allocated_by="ADMIN",
                    )
                    imported_allocations += 1

        self.is_custom_data = True
        self._save_to_disk()

        return {
            "status": "success",
            "message": "Institutional data imported and persisted successfully.",
            "total_departments": len(self.departments),
            "total_faculty": len(email_to_faculty),
            "total_subjects": len(code_to_subject),
            "total_classrooms": len(self.classrooms),
            "total_allocations": imported_allocations,
        }

    def export_data_template(self) -> Dict[str, Any]:
        """Provides an example JSON template for users to paste or upload their original college data."""
        return {
            "clear_existing_mock_data": True,
            "admin_email": "admin@mycollege.edu",
            "admin_password": "ChangeThisPassword123!",
            "admin_name": "Dean of Academics",
            "departments": [
                {"code": "CSE", "name": "Computer Science & Engineering"},
                {"code": "ECE", "name": "Electronics & Communication Engineering"},
                {"code": "EEE", "name": "Electrical & Electronics Engineering"},
                {"code": "MECH", "name": "Mechanical Engineering"},
                {"code": "CIVIL", "name": "Civil Engineering"},
                {"code": "IT", "name": "Information Technology"}
            ],
            "classrooms": [
                {"room_number": "Room 101 (Lecture Hall)", "building": "Academic Block A", "capacity": 70},
                {"room_number": "Room 102 (Lecture Hall)", "building": "Academic Block A", "capacity": 70},
                {"room_number": "Room 103 (Lecture Hall)", "building": "Academic Block A", "capacity": 70},
                {"room_number": "CS-Lab-1 (Computing Lab)", "building": "Tech Center", "capacity": 60},
                {"room_number": "EC-Lab-1 (Hardware Lab)", "building": "Tech Center", "capacity": 60}
            ],
            "faculty": [
                {"full_name": "Prof. John Doe", "email": "john.doe@mycollege.edu", "department_code": "CSE", "password": "facultyPassword123"},
                {"full_name": "Dr. Jane Smith", "email": "jane.smith@mycollege.edu", "department_code": "CSE", "password": "facultyPassword123"},
                {"full_name": "Dr. Robert Lee", "email": "robert.lee@mycollege.edu", "department_code": "ECE", "password": "facultyPassword123"}
            ],
            "subjects": [
                {"code": "CS101", "name": "Programming in Python", "department_code": "CSE", "semester_id": 1, "weekly_hours": 3, "is_lab": False},
                {"code": "CS101L", "name": "Python Programming Lab", "department_code": "CSE", "semester_id": 1, "weekly_hours": 3, "is_lab": True},
                {"code": "EC101", "name": "Digital Logic Design", "department_code": "ECE", "semester_id": 1, "weekly_hours": 3, "is_lab": False}
            ],
            "allocations": [
                {"faculty_email": "john.doe@mycollege.edu", "subject_code": "CS101", "section_name": "A"}
            ]
        }

    def get_database_stats(self) -> Dict[str, Any]:
        total_faculty = len([u for u in self.users.values() if u.role == UserRole.FACULTY])
        return {
            "total_departments": len(self.departments),
            "total_sections": len(self.sections),
            "total_faculty": total_faculty,
            "total_subjects": len(self.subjects),
            "total_classrooms": len(self.classrooms),
            "total_allocations": len(self.allocations),
            "total_generations": len(self.generations),
            "is_demo_mode": not self.is_custom_data,
            "status": "CUSTOM_INSTITUTIONAL_DATA" if self.is_custom_data else "DEMO_MOCK_DATA",
            "message": "Custom Institutional Data is active." if self.is_custom_data else "Demo / Mock Data is active.",
        }

    def add_department(self, code: str, name: str) -> Department:
        code_clean = code.strip().upper()
        for d in self.departments.values():
            if d.code == code_clean:
                raise ValueError(f"Department code '{code_clean}' already exists.")
        new_id = max(self.departments.keys(), default=0) + 1
        dept = Department(id=new_id, code=code_clean, name=name.strip())
        self.departments[new_id] = dept
        self._save_to_disk()
        return dept

    def add_subject(self, code: str, name: str, department_code: str, semester_id: int, is_lab: bool = False, weekly_hours: int = 3) -> Subject:
        code_clean = code.strip().upper()
        if code_clean in [s.code for s in self.subjects.values()]:
            raise ValueError(f"Subject code '{code_clean}' already exists.")
        dept = next((d for d in self.departments.values() if d.code == department_code.strip().upper()), None)
        if not dept:
            raise ValueError(f"Department '{department_code}' not found.")
        new_id = f"sub-{uuid.uuid4().hex[:8]}"
        subject = Subject(
            id=new_id,
            code=code_clean,
            name=name.strip(),
            department_id=dept.id,
            department_code=dept.code,
            semester_id=semester_id,
            weekly_hours=weekly_hours,
            is_lab=is_lab,
        )
        self.subjects[new_id] = subject
        self._save_to_disk()
        return subject

    def add_classroom(self, room_number: str, building: str = "Main Block", capacity: int = 60) -> Classroom:
        new_id = max(self.classrooms.keys(), default=0) + 1
        room = Classroom(
            id=new_id,
            room_number=room_number.strip(),
            building=building.strip(),
            capacity=capacity,
        )
        self.classrooms[new_id] = room
        self._save_to_disk()
        return room

# Singleton instance
db = DataStore()


