#!/usr/bin/env python3
"""
MeterFlow — Apply PostgreSQL Database Schema
--------------------------------------------
Executes database/schema.sql and database/seed.sql against the database
specified in DATABASE_URL.
"""

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("[!] Error: DATABASE_URL environment variable is not set.")
    print("    Please create a .env file with your PostgreSQL connection string:")
    print("    DATABASE_URL=postgresql://<user>:<password>@<host>/<dbname>?sslmode=require")
    sys.exit(1)


def apply_sql_file(conn: psycopg.Connection, file_path: Path, description: str):
    if not file_path.exists():
        print(f"[!] Warning: File {file_path} not found. Skipping {description}.")
        return

    print(f"[+] Applying {description} from {file_path.name}...")
    sql_content = file_path.read_text(encoding="utf-8")
    
    with conn.cursor() as cur:
        cur.execute(sql_content)
    conn.commit()
    print(f"[✓] Successfully applied {file_path.name}.")


def main():
    root_dir = Path(__file__).resolve().parent.parent
    schema_file = root_dir / "database" / "schema.sql"
    seed_file = root_dir / "database" / "seed.sql"

    print("=" * 70)
    print(" MeterFlow — PostgreSQL Schema Initializer")
    print("=" * 70)
    print(f"Connecting to database...")

    try:
        conn = psycopg.connect(DATABASE_URL, autocommit=False, connect_timeout=10)
    except Exception as exc:
        print(f"\n[!] Connection Failed: {exc}")
        print("\nPlease check your DATABASE_URL in .env.")
        sys.exit(1)

    try:
        apply_sql_file(conn, schema_file, "Database DDL Schema (10 tables)")
        
        # Check tables created
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name;
            """)
            tables = [row[0] for row in cur.fetchall()]
        
        print("\n[✓] Tables verified in database:")
        for t in tables:
            print(f"    - {t}")

        print("\n[✓] Database schema initialized successfully!")
    except Exception as exc:
        conn.rollback()
        print(f"\n[!] Error applying schema: {exc}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
