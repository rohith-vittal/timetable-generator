-- ==============================================================================
-- AUTOMATED TIMETABLE GENERATION APPLICATION - RELATIONAL DATABASE SCHEMA
-- Target Database: PostgreSQL 14+
-- Enforces: Strict relational constraints, 1:1 faculty subject allocation,
--           multi-department (CSE, ECE, EEE, MECH) and 6-section (A-F) scheduling,
--           and composite uniqueness to prevent timetable scheduling collisions.
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. ENUMS
CREATE TYPE user_role AS ENUM ('ADMIN', 'FACULTY');
CREATE TYPE schedule_scope AS ENUM ('DAY', 'WEEK', 'YEAR');
CREATE TYPE schedule_status AS ENUM ('DRAFT', 'PUBLISHED', 'ARCHIVED');
CREATE TYPE room_type AS ENUM ('LECTURE_HALL', 'LAB', 'SEMINAR_ROOM');

-- 2. DEPARTMENTS & SECTIONS (6 SECTIONS: A to F)
CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    code VARCHAR(10) UNIQUE NOT NULL, -- 'CSE', 'ECE', 'EEE', 'MECH'
    name VARCHAR(150) NOT NULL
);

CREATE TABLE sections (
    id SERIAL PRIMARY KEY,
    name VARCHAR(10) UNIQUE NOT NULL  -- 'A', 'B', 'C', 'D', 'E', 'F'
);

-- 3. USERS TABLE (AUTHENTICATION & ROLES)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    role user_role NOT NULL DEFAULT 'FACULTY',
    department_id INT NOT NULL REFERENCES departments(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);

-- 4. ACADEMIC STRUCTURE: YEARS & SEMESTERS
CREATE TABLE academic_years (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE, -- e.g., '2026-2027'
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_current BOOLEAN DEFAULT FALSE
);

CREATE TABLE years (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE, -- e.g., 'Year 1', 'Year 2', 'Year 3', 'Year 4'
    academic_level INT NOT NULL UNIQUE -- 1, 2, 3, 4
);

CREATE TABLE semesters (
    id SERIAL PRIMARY KEY,
    year_id INT NOT NULL REFERENCES years(id) ON DELETE CASCADE,
    name VARCHAR(50) NOT NULL, -- e.g., 'Semester 1', 'Semester 2'
    term_number INT NOT NULL,  -- 1 through 8
    academic_year_id INT NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
    UNIQUE (year_id, term_number)
);

CREATE INDEX idx_semesters_year ON semesters(year_id);

-- 5. SUBJECTS
CREATE TABLE subjects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(20) NOT NULL UNIQUE,     -- e.g., 'CS301', 'EC301'
    name VARCHAR(150) NOT NULL,            -- e.g., 'Database Management Systems'
    department_id INT NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    semester_id INT NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    weekly_hours INT NOT NULL DEFAULT 4,   -- Number of 1-hour slots required per week
    credits INT NOT NULL DEFAULT 3,
    is_lab BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_subjects_department ON subjects(department_id);
CREATE INDEX idx_subjects_semester ON subjects(semester_id);

-- 6. FACULTY ALLOCATIONS (ADMIN-CONTROLLED OR FACULTY-PREFERENCE)
-- Crucial Constraint: Each faculty member is restricted to choosing ONLY ONE subject.
-- Admin has the authority to allocate faculty to specific Year, Semester, Department, and Section.
CREATE TABLE faculty_allocations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    faculty_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    department_id INT NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    year_id INT NOT NULL REFERENCES years(id) ON DELETE CASCADE,
    semester_id INT NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    section_id INT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    academic_year_id INT NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
    allocated_by VARCHAR(50) NOT NULL DEFAULT 'ADMIN',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_allocations_faculty ON faculty_allocations(faculty_id);
CREATE INDEX idx_allocations_subject ON faculty_allocations(subject_id);
CREATE INDEX idx_allocations_dept_sec ON faculty_allocations(department_id, section_id);

-- 7. TIME SLOTS & CLASSROOMS
CREATE TABLE time_slots (
    id SERIAL PRIMARY KEY,
    day_of_week INT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6), -- 0=Monday ... 4=Friday
    slot_index INT NOT NULL CHECK (slot_index BETWEEN 1 AND 12),   -- Period 1, 2, 3...
    start_time TIME NOT NULL,                                     -- e.g., '09:00:00'
    end_time TIME NOT NULL,                                       -- e.g., '10:00:00'
    is_break BOOLEAN DEFAULT FALSE,                               -- Lunch break
    UNIQUE (day_of_week, slot_index)
);

CREATE TABLE classrooms (
    id SERIAL PRIMARY KEY,
    room_number VARCHAR(50) NOT NULL UNIQUE,
    building VARCHAR(100) NOT NULL,
    capacity INT NOT NULL DEFAULT 60,
    room_type room_type DEFAULT 'LECTURE_HALL',
    is_active BOOLEAN DEFAULT TRUE
);

-- 8. TIMETABLE GENERATION RECORD
CREATE TABLE timetable_generations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(150) NOT NULL,
    scope schedule_scope NOT NULL,       -- 'DAY', 'WEEK', 'YEAR'
    status schedule_status NOT NULL DEFAULT 'DRAFT',
    academic_year_id INT NOT NULL REFERENCES academic_years(id),
    target_date DATE NULL,               -- Only populated when scope = 'DAY'
    created_by UUID NOT NULL REFERENCES users(id),
    algorithm_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP WITH TIME ZONE NULL
);

-- 9. TIMETABLE ENTRIES (THE GENERATED SCHEDULE)
CREATE TABLE timetable_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    generation_id UUID NOT NULL REFERENCES timetable_generations(id) ON DELETE CASCADE,
    calendar_date DATE NULL,
    day_of_week INT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    time_slot_id INT NOT NULL REFERENCES time_slots(id) ON DELETE CASCADE,
    department_id INT NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    section_id INT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    faculty_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    semester_id INT NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    classroom_id INT NOT NULL REFERENCES classrooms(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- =========================================================================
    -- CRITICAL CONFLICT PREVENTION UNIQUE CONSTRAINTS
    -- =========================================================================
    
    -- Constraint 1: A faculty member cannot be scheduled in two places at the same time
    CONSTRAINT uq_faculty_slot UNIQUE NULLS NOT DISTINCT (
        generation_id, calendar_date, day_of_week, time_slot_id, faculty_id
    ),

    -- Constraint 2: A specific Section cohort (Dept + Semester + Section) cannot have two subjects simultaneously
    CONSTRAINT uq_cohort_slot UNIQUE NULLS NOT DISTINCT (
        generation_id, calendar_date, day_of_week, time_slot_id, department_id, semester_id, section_id
    ),

    -- Constraint 3: A physical classroom cannot host two sessions simultaneously
    CONSTRAINT uq_classroom_slot UNIQUE NULLS NOT DISTINCT (
        generation_id, calendar_date, day_of_week, time_slot_id, classroom_id
    )
);

CREATE INDEX idx_entries_generation ON timetable_entries(generation_id);
CREATE INDEX idx_entries_faculty ON timetable_entries(faculty_id);
CREATE INDEX idx_entries_dept_sec ON timetable_entries(department_id, section_id);
CREATE INDEX idx_entries_semester ON timetable_entries(semester_id);
