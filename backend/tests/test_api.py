from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_root_serves_ui():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ChronoScheduler" in response.text

def test_auth_login_admin():
    # Valid Admin Login
    res = client.post("/api/auth/login", json={
        "email": "admin@university.edu",
        "password": "admin123"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["role"] == "ADMIN"
    assert "token" in data

    # Invalid Password
    res_bad = client.post("/api/auth/login", json={
        "email": "admin@university.edu",
        "password": "wrongpassword"
    })
    assert res_bad.status_code == 401

def test_auth_login_faculty():
    # Valid Faculty Login
    res = client.post("/api/auth/login", json={
        "email": "grace.hopper@univ.edu",
        "password": "faculty123"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["role"] == "FACULTY"
    assert data["user"]["department_code"] == "CSE"

def test_metadata_includes_departments_and_6_sections():
    response = client.get("/api/metadata")
    assert response.status_code == 200
    data = response.json()
    assert "departments" in data
    assert len(data["departments"]) >= 4
    dept_codes = [d["code"] for d in data["departments"]]
    assert "CSE" in dept_codes and "ECE" in dept_codes and "EEE" in dept_codes and "MECH" in dept_codes

    assert "sections" in data
    assert len(data["sections"]) == 6
    sec_names = [s["name"] for s in data["sections"]]
    assert sec_names == ["A", "B", "C", "D", "E", "F"]

def test_admin_authority_to_allocate_classes_for_sections():
    """
    Test that Admin has authority to allocate a faculty member to a specific
    department, subject, year, semester, and section (e.g., Section C).
    """
    admin_payload = {
        "faculty_id": "fac-cse-01",
        "subject_id": "sub-cs-101",
        "department_id": 1, # CSE
        "year_id": 1,
        "semester_id": 1,
        "section_id": 3, # Section C
        "academic_year_id": 1,
        "allocated_by": "ADMIN",
    }
    res = client.post("/api/admin/allocate", json=admin_payload)
    assert res.status_code == 201
    data = res.json()
    assert data["subject_code"] == "CS101"
    assert data["department_code"] == "CSE"
    assert data["section_name"] == "C"
    assert data["allocated_by"] == "ADMIN"

    # Reset back to Section A for subsequent tests
    admin_payload["section_id"] = 1
    client.post("/api/admin/allocate", json=admin_payload)

def test_faculty_allocation_api_enforces_one_subject():
    # 1. Allocate Dr. Grace Hopper (fac-cse-01) to CS101 in Section A
    payload = {
        "faculty_id": "fac-cse-01",
        "subject_id": "sub-cs-101",
        "department_id": 1,
        "year_id": 1,
        "semester_id": 1,
        "section_id": 1,
        "academic_year_id": 1,
    }
    res = client.post("/api/faculty/allocate", json=payload)
    assert res.status_code == 201
    assert res.json()["subject_code"] == "CS101"

    # 2. Check allocation
    res = client.get("/api/faculty/allocation/fac-cse-01")
    assert res.status_code == 200
    assert res.json()["subject_id"] == "sub-cs-101"

def test_admin_generation_publishing_and_section_filtering():
    # 1. Trigger timetable generation (WEEK scope)
    gen_payload = {
        "title": "Fall 2026 Master Multi-Dept Timetable",
        "scope": "WEEK",
        "academic_year_id": 1,
    }
    gen_res = client.post("/api/admin/generate", json=gen_payload)
    assert gen_res.status_code == 201
    gen_data = gen_res.json()
    assert gen_data["status"] == "DRAFT"
    gen_id = gen_data["id"]

    # 2. Publish timetable
    pub_res = client.post(f"/api/admin/publish/{gen_id}")
    assert pub_res.status_code == 200
    assert pub_res.json()["status"] == "PUBLISHED"

    # 3. Faculty can view their schedule
    fac_res = client.get(f"/api/faculty/timetable/fac-cse-01?generation_id={gen_id}")
    assert fac_res.status_code == 200
    entries = fac_res.json()
    assert len(entries) > 0
    assert all(e["faculty_id"] == "fac-cse-01" for e in entries)

    # 4. Admin filter by Department (CSE = 1)
    dept_res = client.get(f"/api/admin/timetables?generation_id={gen_id}&department_id=1")
    assert dept_res.status_code == 200
    cse_entries = dept_res.json()
    assert len(cse_entries) > 0
    assert all(e["department_id"] == 1 for e in cse_entries)

    # 5. Admin filter by Section (Section A = 1)
    sec_res = client.get(f"/api/admin/timetables?generation_id={gen_id}&section_id=1")
    assert sec_res.status_code == 200
    sec_entries = sec_res.json()
    assert len(sec_entries) > 0
    assert all(e["section_id"] == 1 for e in sec_entries)

    # 6. Admin CSV export includes Department and Section
    csv_res = client.get(f"/api/admin/timetables/{gen_id}/export")
    assert csv_res.status_code == 200
    assert "Department,Section" in csv_res.text
    assert "Section A" in csv_res.text

def test_auth_register_faculty_and_admin():
    from app.storage import db
    for uid, u in list(db.users.items()):
        if u.email in ["sarah.connor@univ.edu", "admin.assistant@university.edu"]:
            db.users.pop(uid, None)

    # 1. Register a new faculty member
    fac_payload = {
        "email": "sarah.connor@univ.edu",
        "password": "facultysecure",
        "full_name": "Dr. Sarah Connor",
        "role": "FACULTY",
        "department_id": 1,
    }
    res = client.post("/api/auth/register", json=fac_payload)
    assert res.status_code == 201
    data = res.json()
    assert data["user"]["email"] == "sarah.connor@univ.edu"
    assert data["user"]["role"] == "FACULTY"
    assert data["user"]["department_code"] == "CSE"
    assert "token" in data

    # 2. Login with new faculty credentials
    login_res = client.post("/api/auth/login", json={"email": "sarah.connor@univ.edu", "password": "facultysecure"})
    assert login_res.status_code == 200
    assert login_res.json()["user"]["full_name"] == "Dr. Sarah Connor"

    # 3. Register a new Admin
    admin_payload = {
        "email": "admin.assistant@university.edu",
        "password": "adminsecure",
        "full_name": "Marcus Wright",
        "role": "ADMIN",
    }
    admin_res = client.post("/api/auth/register", json=admin_payload)
    assert admin_res.status_code == 201
    assert admin_res.json()["user"]["role"] == "ADMIN"

def test_auth_register_duplicate_email_fails():
    payload = {
        "email": "grace.hopper@univ.edu", # existing email
        "password": "newpassword",
        "full_name": "Dr. Duplicate Grace",
        "role": "FACULTY",
    }
    res = client.post("/api/auth/register", json=payload)
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"]

def test_admin_bot_situational_generation():
    bot_payload = {
        "prompt": "Create an emergency timetable for tomorrow with 0 blank slots and balanced labs",
        "target_date": "2026-10-19",
    }
    res = client.post("/api/admin/bot-generate", json=bot_payload)
    assert res.status_code == 201
    data = res.json()
    assert "bot_message" in data
    assert "ChronoBot" in data["bot_message"]
    assert data["scope"] == "DAY"
    assert data["insights"]["conflicts_detected"] == 0
    assert data["insights"]["total_periods_scheduled"] > 0
    assert data["insights"]["database_records_consulted"] > 0
    assert len(data["generation"]["entries"]) > 0

def test_auth_guard_invalid_token_rejected():
    res = client.post(
        "/api/admin/generate",
        json={"title": "Test Schedule", "scope": "WEEK", "academic_year_id": 1},
        headers={"Authorization": "Bearer bad-token-12345"}
    )
    assert res.status_code == 401
    assert "Invalid or expired session token" in res.json()["detail"]

def test_faculty_cannot_access_admin_endpoint():
    res = client.post(
        "/api/admin/generate",
        json={"title": "Test Schedule", "scope": "WEEK", "academic_year_id": 1},
        headers={"Authorization": "Bearer tok-faculty-valid-session"}
    )
    assert res.status_code == 403
    assert "Administrative privileges required" in res.json()["detail"]


