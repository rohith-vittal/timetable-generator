# Automated Timetable Generation Engine & API

A full-stack, conflict-free automated scheduling system that generates academic timetables based on faculty availability, subjects, years, and semesters. Supports multi-scope generation: **1 Day**, **1 Week**, and **1 Academic Year**.

---

## 🌟 Core Highlights & Architectural Features

1. **Strict 1:1 Faculty-Subject Allocation**:
   - Each faculty member is restricted to selecting exactly one subject per semester.
   - Enforced at both the API level and the database schema level (`UNIQUE (faculty_id)` in `faculty_allocations`).

2. **Constraint Programming Engine (CP-SAT & CSP)**:
   - Uses Google OR-Tools CP-SAT (with a pure-Python MRV/Forward Checking backtracking fallback) to mathematically guarantee **zero scheduling conflicts**:
     - **No Faculty Overlap**: A teacher is never assigned to two classes at the same time.
     - **No Cohort/Semester Overlap**: Students in a given semester/year cannot have concurrent lectures.
     - **No Classroom Double-Booking**: Physical rooms are mutually exclusive per time slot.
     - **Break Slot Protection**: Lunch breaks and recess periods are strictly preserved.
     - **Workload Spreading**: Lectures are balanced across weekdays (avoiding multi-class clumping).

3. **Flexible Generation Scopes**:
   - **1 Day**: Produces a conflict-free schedule for a specific date or day of the week.
   - **1 Week**: Produces the canonical recurring master weekly template (Monday – Friday).
   - **1 Year**: Projects the weekly master schedule across the full academic calendar year, tagging calendar dates and handling semester boundaries.

4. **Role-Based Access Control (RBAC)**:
   - **Faculty Dashboard**: Allows teachers to submit subject preferences (Year, Semester, Subject) and view their personalized read-only timetable once published.
   - **Admin Control Panel**: Triggers automatic timetable generation with scope selection, filters master schedules by Year, Semester, and Faculty member, and exports schedules to CSV.

---

## 📁 Repository Structure

```
timetable-generator/
├── schema.sql                 # Production PostgreSQL relational schema with composite constraints
└── backend/
    ├── requirements.txt       # Dependencies (FastAPI, Uvicorn, OR-Tools, Pydantic, Pytest)
    ├── run.py                 # Quick-start script
    ├── app/
    │   ├── __init__.py
    │   ├── main.py            # FastAPI entrypoint with CORS
    │   ├── models.py          # Domain data models & Enums
    │   ├── schemas.py         # Pydantic v2 validation models
    │   ├── solver.py          # Core CP-SAT & Backtracking CSP Engine
    │   ├── storage.py         # Relational data store enforcing 1:1 allocation
    │   └── routers/
    │       ├── faculty.py     # Faculty allocation & personalized dashboard
    │       ├── admin.py       # Admin generation, filtering, publishing, CSV export
    │       └── metadata.py    # Form lookups for Years, Semesters, Subjects, Faculty
    └── tests/
        ├── test_solver.py     # Algorithmic conflict-freedom & constraint tests
        └── test_api.py        # REST API endpoint integration tests
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+
- (Optional) PostgreSQL 14+ (if deploying to production; the backend includes an out-of-the-box relational in-memory store for instant evaluation).

### 2. Installation

```bash
cd backend
python -m pip install -r requirements.txt
```

### 3. Run the Automated Tests

Verify that all constraints, conflict resolution rules, and API endpoints are 100% compliant:

```bash
python -m pytest tests/ -v
```

### 4. Start the Backend API

```bash
python run.py
```

The server will start at `http://localhost:8000`.
- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 📡 Key API Endpoints

### Faculty Interface
- `POST /api/faculty/allocate`: Submit subject preference (strictly validates 1 subject per teacher, matching Year & Semester).
- `GET /api/faculty/allocation/{faculty_id}`: Inspect the faculty member's current single subject preference.
- `GET /api/faculty/timetable/{faculty_id}`: Read-only personal schedule (supports filtering by `generation_id`, `view_date`, or `day_of_week`).

### Admin Interface
- `POST /api/admin/generate`: Triggers the scheduling engine with payload:
  ```json
  {
    "title": "Fall 2026 Academic Timetable",
    "scope": "WEEK", // Options: "DAY", "WEEK", "YEAR"
    "academic_year_id": 1,
    "target_date": "2026-10-19" // Required if scope is "DAY"
  }
  ```
- `POST /api/admin/publish/{generation_id}`: Publishes the draft schedule to make it live for faculty dashboards.
- `GET /api/admin/timetables`: Master global viewer with multi-criteria query parameters:
  - `?year_id=1`
  - `?semester_id=1`
  - `?faculty_id=fac-001`
  - `?day_of_week=0`
- `GET /api/admin/timetables/{generation_id}/export`: Exports the timetable directly to CSV.
