#!/usr/bin/env python3
"""
ChronoScheduler Database Management & Original Data Import CLI Utility.

Usage:
    # 1. Check current database state
    python manage_data.py --status

    # 2. Export a clean JSON template to fill in real institution data
    python manage_data.py --template my_college_template.json

    # 3. Clear all fake/mock data (leaves an empty, clean slate)
    python manage_data.py --clear-mock

    # 4. Import your original real data JSON file into the database
    python manage_data.py --import my_real_college_data.json

    # 5. Restore the pre-packaged demo dataset anytime
    python manage_data.py --reset-demo
"""

import sys
import os
import json
import argparse
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.storage import db
from app.models import UserRole

def print_banner():
    print("=" * 70)
    print("  ⏱️  ChronoScheduler Enterprise - Database & Institutional Data CLI")
    print("=" * 70)

def show_status():
    print_banner()
    stats = db.get_database_stats()
    print(f"\n[Database Status]: {stats['status']}")
    print(f"[Database Engine]: {stats.get('database_engine', 'SQLite (SQLAlchemy Relational)')}")
    print(f"[Database Target]: {stats.get('database_target', str(backend_dir / 'data' / 'timetable.db'))}")
    print(f"[Mode]: {'DEMO / MOCK DATA (Alan Turing, Grace Hopper, etc.)' if stats['is_demo_mode'] else 'ORIGINAL / REAL INSTITUTIONAL DATA'}")
    print("-" * 50)
    print(f"  • Total Departments: {stats['total_departments']}")
    print(f"  • Total Sections:    {stats['total_sections']} (Sections A-F)")
    print(f"  • Total Faculty:     {stats['total_faculty']}")
    print(f"  • Total Subjects:    {stats['total_subjects']}")
    print(f"  • Total Classrooms:  {stats['total_classrooms']}")
    print(f"  • Total Allocations: {stats['total_allocations']}")
    print(f"  • Timetables:        {stats['total_generations']}")
    print("-" * 50)
    print(f"Relational DB: {backend_dir / 'data' / 'timetable.db'}")
    print(f"JSON Backup:   {backend_dir / 'data' / 'timetable_store.json'}\n")

def clear_mock():
    print_banner()
    print("\n[!] Wiping all fake/mock faculty, mock subjects, mock classrooms, and allocations...")
    res = db.clear_mock_data(preserve_admin=True)
    print(f"SUCCESS: {res['message']}")
    print(f"Remaining active accounts: {res['remaining_users']}")
    print("\nThe database is now a clean slate ready for your real institutional data.")
    print("Next step: Use `python manage_data.py --import <your_file.json>` or upload via the Admin UI.\n")

def export_template(filepath: str):
    print_banner()
    template = db.export_data_template()
    out_path = Path(filepath)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2)
    print(f"\nSUCCESS: Institutional Data Template exported to: {out_path.resolve()}")
    print("Edit this file with your real faculty, subjects, and rooms, then run:")
    print(f"  python manage_data.py --import \"{out_path.name}\"\n")

def import_real_data(filepath: str):
    print_banner()
    in_path = Path(filepath)
    if not in_path.exists():
        print(f"\nERROR: File not found: {in_path.resolve()}")
        sys.exit(1)

    with open(in_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"\nERROR: Invalid JSON file: {e}")
            sys.exit(1)

    print(f"\n[*] Validating and importing original data from: {in_path.resolve()} ...")
    res = db.import_institutional_data(data)
    print(f"\nSUCCESS: {res['message']}")
    print("-" * 50)
    print(f"  • Imported Departments: {res['total_departments']}")
    print(f"  • Imported Faculty:     {res['total_faculty']}")
    print(f"  • Imported Subjects:    {res['total_subjects']}")
    print(f"  • Configured Classrooms:{res['total_classrooms']}")
    print(f"  • Active Allocations:   {res['total_allocations']}")
    print("-" * 50)
    print("Your real institutional database is now active and saved permanently.\n")

def reset_demo():
    print_banner()
    print("\n[*] Restoring default demo dataset...")
    res = db.reset_to_demo_data()
    print(f"\nSUCCESS: {res['message']}")
    print(f"Total Demo Faculty: {res['total_faculty']}, Subjects: {res['total_subjects']}, Allocations: {res['total_allocations']}\n")

def main():
    parser = argparse.ArgumentParser(description="ChronoScheduler Data Management CLI")
    parser.add_argument("--status", action="store_true", help="Display current database counts and mode")
    parser.add_argument("--clear-mock", action="store_true", help="Clear all mock/fake faculty, subjects, rooms, and allocations")
    parser.add_argument("--template", type=str, nargs="?", const="institution_data_template.json", help="Export clean JSON template for real data")
    parser.add_argument("--import", dest="import_file", type=str, help="Import a JSON file containing real institutional data")
    parser.add_argument("--reset-demo", action="store_true", help="Reset database back to the demo/mock dataset")

    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.clear_mock:
        clear_mock()
    elif args.template:
        export_template(args.template)
    elif args.import_file:
        import_real_data(args.import_file)
    elif args.reset_demo:
        reset_demo()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
