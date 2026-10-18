# Automated Timetable Generation Engine & Portal

A full-stack, conflict-free automated scheduling system that generates academic timetables across **multiple engineering departments (CSE, ECE, EEE, MECH)** and **6 distinct sections (Section A to Section F)**, supporting flexible time horizons (**1 Day**, **1 Week**, and **1 Academic Year**).

---

## 🌟 Key Features & Updates

### 1. Authentication & Role-Based Login
- **Dual Role Portals**: Separate, secure experiences for **Faculty** and **Institution Administrators**.
- **Login Modal & Endpoints**: API authentication at `/api/auth/login` and interactive frontend modal with pre-configured demo logins:
  - 🛡️ **Admin**: `admin@university.edu` / `admin123` (Dr. Alan Turing, Dean)
  - 👨‍🏫 **CSE Faculty**: `grace.hopper@univ.edu` / `faculty123` (Dr. Grace Hopper)
  - 📡 **ECE Faculty**: `claude.shannon@univ.edu` / `faculty123` (Dr. Claude Shannon)
  - ⚡ **EEE Faculty**: `nikola.tesla@univ.edu` / `faculty123` (Dr. Nikola Tesla)
  - ⚙️ **MECH Faculty**: `james.watt@univ.edu` / `faculty123` (Dr. James Watt)

### 2. Admin Authority to Allocate Classes for Faculty & Sections
- Institution administrators have complete authority to assign faculty members to specific **Departments**, **Years**, **Semesters**, **Subjects**, and **Sections**.
- **Crucial Invariant**: Each faculty member is restricted to **exactly 1 subject**. Assigning a faculty to a new subject replaces their previous allocation.

### 3. Multi-Department & 6 Sections Architecture
- **Departments Supported**:
  - `CSE` (Computer Science & Engineering)
  - `ECE` (Electronics & Communication Engineering)
  - `EEE` (Electrical & Electronics Engineering)
  - `MECH` (Mechanical Engineering)
- **6 Sections Supported**: Section A, Section B, Section C, Section D, Section E, Section F.
- **Section Cohort Constraint**: The Constraint Programming (CP-SAT) engine guarantees that students in a specific section (e.g., *ECE - Year 2 - Semester 3 - Section C*) are never scheduled for two classes simultaneously.

### 4. Conflict-Free Constraint Programming Engine (CP-SAT)
- Guarantees **0 collisions** across all:
  1. **Faculty Overlaps**: No teacher assigned to 2 sections simultaneously.
  2. **Section Overlaps**: No cohort assigned to 2 subjects in the same period.
  3. **Classroom Overlaps**: No room double-booked.
  4. **Lunch Break Integrity**: Reserved institutional break slot (Period 4) unassigned.
  5. **Workload Spreading**: Lectures distributed across weekdays.

---

## 📁 Repository Structure

```
timetable-generator/
├── schema.sql                 # PostgreSQL relational schema (Depts, 6 Sections, Composite Constraints)
└── backend/
    ├── requirements.txt       # Dependencies (FastAPI, Uvicorn, OR-Tools, Pydantic, Pytest)
    ├── run.py                 # Server startup script
    ├── static/
    │   └── index.html         # Interactive Web Application UI
    ├── app/
    │   ├── main.py            # FastAPI entrypoint serving UI & API
    │   ├── models.py          # Models: Department, Section, User, Subject, Allocation
    │   ├── schemas.py         # Request/Response validation schemas & Auth
    │   ├── solver.py          # CP-SAT & Backtracking CSP Engine (Multi-Dept & 6-Sec)
    │   ├── storage.py         # In-memory store with relational integrity checks
    │   └── routers/
    │       ├── auth.py        # Login & demo account endpoints
    │       ├── admin.py       # Admin allocation authority, engine controls, multi-filters, CSV export
    │       ├── faculty.py     # Faculty allocation & personalized dashboard
    │       └── metadata.py    # Lookups for Depts, Sections, Years, Subjects, Faculty
    └── tests/
        ├── test_solver.py     # Algorithmic conflict-freedom & constraint tests
        └── test_api.py        # REST API endpoint & auth integration tests
```

---

## 🚀 How to Run & View the Application

### Option A: Open the Interactive UI Directly
Double-click or open in your browser:
* **[Interactive Portal Preview](file:///C:/Users/vitta/.gemini/antigravity/brain/4ce471c2-d38b-4eb5-bc9d-f4440f2d0ca6/app_preview.html)**

### Option B: Run the Full-Stack Server
```powershell
cd C:\Users\vitta\.gemini\antigravity\scratch\timetable-generator\backend
python run.py
```

Then visit:
- **Interactive Web App**: [http://localhost:8000/](http://localhost:8000/)
- **Swagger API Explorer**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Run Tests
```powershell
python -m pytest tests/ -v
```
*(All 13 unit and integration tests verify 100% compliance).*
