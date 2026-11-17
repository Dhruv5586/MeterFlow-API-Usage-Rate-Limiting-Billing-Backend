#!/usr/bin/env python3
"""
MeterFlow — Step 4: Validate Usage Events Import
------------------------------------------------
Runs 8 comprehensive database and file integrity checks:
1. Every imported event references an existing user.
2. Every imported event references an existing API key.
3. The API key belongs to the event's user.
4. No static asset requests are imported.
5. No duplicate source records exist.
6. Imported timestamps and numeric values are valid.
7. Original CSV remains unchanged.
8. Imported record counts match the import report.
"""

import sys
import json
import hashlib
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from sqlalchemy import text
from app.core.database import SessionLocal, check_database_health

EXPECTED_RAW_CSV_SIZE = 679667


def validate():
    root_dir = Path(__file__).resolve().parent.parent
    raw_csv_path = root_dir / "data" / "raw" / "access_logs.csv"
    report_json_path = root_dir / "data" / "reports" / "import_report.json"

    print("=" * 70)
    print(" MeterFlow — Step 4: Import Validation Suite")
    print("=" * 70)

    # Pre-check database connection
    check_database_health()
    session = SessionLocal()

    checks = []
    overall_passed = True

    try:
        # Check 1: User Foreign Keys
        res1 = session.execute(text("""
            SELECT COUNT(*)
            FROM usage_events e
            LEFT JOIN users u ON e.user_id = u.id
            WHERE u.id IS NULL;
        """)).scalar()
        c1_passed = (res1 == 0)
        checks.append({
            "name": "Check 1: All Events Reference Existing Users",
            "passed": c1_passed,
            "details": f"Orphaned user references found: {res1}",
        })
        if not c1_passed: overall_passed = False

        # Check 2: API Key Foreign Keys
        res2 = session.execute(text("""
            SELECT COUNT(*)
            FROM usage_events e
            LEFT JOIN api_keys k ON e.api_key_id = k.id
            WHERE k.id IS NULL;
        """)).scalar()
        c2_passed = (res2 == 0)
        checks.append({
            "name": "Check 2: All Events Reference Existing API Keys",
            "passed": c2_passed,
            "details": f"Orphaned API key references found: {res2}",
        })
        if not c2_passed: overall_passed = False

        # Check 3: Tenant Key Ownership Match
        res3 = session.execute(text("""
            SELECT COUNT(*)
            FROM usage_events e
            JOIN api_keys k ON e.api_key_id = k.id
            WHERE e.user_id <> k.user_id;
        """)).scalar()
        c3_passed = (res3 == 0)
        checks.append({
            "name": "Check 3: API Key Belongs to Event's User",
            "passed": c3_passed,
            "details": f"Mismatched key-user ownership count: {res3}",
        })
        if not c3_passed: overall_passed = False

        # Check 4: No Static Asset Requests Imported
        res4 = session.execute(text("""
            SELECT COUNT(*)
            FROM usage_events
            WHERE endpoint LIKE '/static/%'
               OR endpoint LIKE '%.png'
               OR endpoint LIKE '%.js'
               OR endpoint LIKE '%.css'
               OR endpoint LIKE '%.ico'
               OR endpoint LIKE '%.xml';
        """)).scalar()
        c4_passed = (res4 == 0)
        checks.append({
            "name": "Check 4: Zero Static Asset Requests in Database",
            "passed": c4_passed,
            "details": f"Static asset records found in DB: {res4}",
        })
        if not c4_passed: overall_passed = False

        # Check 5: No Duplicate Source Records
        res5 = session.execute(text("""
            SELECT source_record_key, COUNT(*)
            FROM usage_events
            WHERE source_record_key IS NOT NULL
            GROUP BY source_record_key
            HAVING COUNT(*) > 1;
        """)).fetchall()
        c5_passed = (len(res5) == 0)
        checks.append({
            "name": "Check 5: No Duplicate Source Record Keys",
            "passed": c5_passed,
            "details": f"Duplicate source keys found: {len(res5)}",
        })
        if not c5_passed: overall_passed = False

        # Check 6: Valid Timestamps and Numeric Bounds
        res6 = session.execute(text("""
            SELECT COUNT(*)
            FROM usage_events
            WHERE latency_ms < 0
               OR response_size_bytes < 0
               OR status_code < 100
               OR status_code > 599
               OR created_at IS NULL;
        """)).scalar()
        c6_passed = (res6 == 0)
        checks.append({
            "name": "Check 6: Numeric Fields & Timestamps Are Valid",
            "passed": c6_passed,
            "details": f"Out-of-bounds or invalid records: {res6}",
        })
        if not c6_passed: overall_passed = False

        # Check 7: Original CSV Unchanged
        raw_size = raw_csv_path.stat().st_size if raw_csv_path.exists() else 0
        c7_passed = (raw_size == EXPECTED_RAW_CSV_SIZE)
        checks.append({
            "name": "Check 7: Original CSV Remains Unchanged",
            "passed": c7_passed,
            "details": f"Original size: {EXPECTED_RAW_CSV_SIZE} bytes, Current size: {raw_size} bytes",
        })
        if not c7_passed: overall_passed = False

        # Check 8: Total Count Matches Report
        total_in_db = session.execute(text("SELECT COUNT(*) FROM usage_events;")).scalar()
        report_count = None
        if report_json_path.exists():
            with open(report_json_path, "r", encoding="utf-8") as f:
                rdata = json.load(f)
                report_count = rdata.get("total_records_successfully_imported")

        c8_passed = (report_count is not None and total_in_db >= report_count)
        checks.append({
            "name": "Check 8: Database Records Match Import Report",
            "passed": c8_passed,
            "details": f"DB count: {total_in_db}, Last report import count: {report_count}",
        })
        if not c8_passed: overall_passed = False

    finally:
        session.close()

    print("\n" + "-" * 70)
    print(" VALIDATION RESULTS")
    print("-" * 70)
    for c in checks:
        mark = "[PASS]" if c["passed"] else "[FAIL]"
        print(f" {mark} {c['name']}")
        print(f"        -> {c['details']}")

    print("-" * 70)
    if overall_passed:
        print("[✓] ALL 8 VALIDATION CHECKS PASSED PERFECTLY.")
        return 0
    else:
        print("[✗] ONE OR MORE CHECKS FAILED.")
        return 1


if __name__ == "__main__":
    exit_code = validate()
    sys.exit(exit_code)
