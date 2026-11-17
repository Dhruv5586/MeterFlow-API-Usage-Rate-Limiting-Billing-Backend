#!/usr/bin/env python3
"""
MeterFlow — Step 3: Create Demo Users and API Keys
--------------------------------------------------
This script creates 3 realistic enterprise demo users, generates cryptographically
secure API keys (hashed using SHA-256), and links active subscriptions.

Requirements satisfied:
- Connects to existing PostgreSQL database using DATABASE_URL (via python-dotenv / psycopg)
- Generates 3 enterprise demo users with realistic data and valid lowercase emails
- Generates secure random API keys with secrets module
- Stores ONLY 64-char lowercase hexadecimal SHA-256 hashes (never plaintext)
- Assigns valid subscriptions with valid 30-day periods
- Uses database transactions with automatic rollback on error
- Fully idempotent: multiple executions will not produce duplicates or errors
- Provides automated post-insert validation routine
"""

import os
import sys
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Any

# Attempt to load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg
from psycopg.rows import dict_row

# Configuration
DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/meterflow"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

# Demo User Specifications
DEMO_USERS: List[Dict[str, Any]] = [
    {
        "id": "20000000-0000-4000-8000-000000000001",
        "email": "admin@technova.io",
        "display_name": "TechNova Solutions",
        "status": "active",
        "plan_code": "enterprise",
        "plan_id": "00000000-0000-4000-8000-000000000003",
        "key_id": "40000000-0000-4000-8000-000000000001",
        "key_name": "TechNova Production Key",
        "sub_id": "30000000-0000-4000-8000-000000000001",
    },
    {
        "id": "20000000-0000-4000-8000-000000000002",
        "email": "engineering@cloudsphere.dev",
        "display_name": "CloudSphere Technologies",
        "status": "active",
        "plan_code": "pro",
        "plan_id": "00000000-0000-4000-8000-000000000002",
        "key_id": "40000000-0000-4000-8000-000000000002",
        "key_name": "CloudSphere Ingestion Key",
        "sub_id": "30000000-0000-4000-8000-000000000002",
    },
    {
        "id": "20000000-0000-4000-8000-000000000003",
        "email": "ops@databridge.net",
        "display_name": "DataBridge Systems",
        "status": "active",
        "plan_code": "free",
        "plan_id": "00000000-0000-4000-8000-000000000001",
        "key_id": "40000000-0000-4000-8000-000000000003",
        "key_name": "DataBridge Analytics Key",
        "sub_id": "30000000-0000-4000-8000-000000000003",
    },
]


def generate_secure_api_key() -> Tuple[str, str, str]:
    """
    Generates a high-entropy API key using Python's secrets module.
    Returns:
        (full_plaintext_key, key_prefix, key_hash_hex)
    """
    # 32 bytes of cryptographic randomness = 43 URL-safe characters
    random_secret = secrets.token_urlsafe(32)
    full_key = f"mf_live_{random_secret}"
    
    # Prefix is non-secret, used for UI display and identification
    prefix = full_key[:16]
    
    # Key hash is SHA-256 digest in lowercase hexadecimal (64 characters)
    # Strictly satisfies database constraint: CHECK (key_hash ~ '^[0-9a-f]{64}$')
    key_hash = hashlib.sha256(full_key.encode("utf-8")).hexdigest().lower()
    
    return full_key, prefix, key_hash


def create_demo_data(conn: psycopg.Connection, show_keys: bool = True) -> Dict[str, Any]:
    """
    Inserts demo users, API keys, and subscriptions inside a safe database transaction.
    Uses ON CONFLICT to ensure strict idempotency.
    """
    now = datetime.now(timezone.utc)
    period_end = now + timedelta(days=30)
    expires_at = now + timedelta(days=365)
    
    generated_keys_output: List[Dict[str, str]] = []
    
    with conn.transaction():
        with conn.cursor() as cur:
            # 1. Ensure required subscription plans exist
            plans_to_ensure = [
                ("00000000-0000-4000-8000-000000000001", "free", "Free", 0.00, "USD", "month"),
                ("00000000-0000-4000-8000-000000000002", "pro", "Pro", 29.00, "USD", "month"),
                ("00000000-0000-4000-8000-000000000003", "enterprise", "Enterprise", 299.00, "USD", "month"),
            ]
            for pid, code, name, price, currency, interval in plans_to_ensure:
                cur.execute(
                    """
                    INSERT INTO subscription_plans (id, code, name, price, currency, billing_interval, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                    ON CONFLICT (id) DO NOTHING;
                    """,
                    (pid, code, name, price, currency, interval),
                )
            
            # 2. Insert Demo Users
            for user in DEMO_USERS:
                # Generate a dummy password hash (e.g. SHA-256 digest of a demo secret)
                dummy_pwd_hash = hashlib.sha256(f"demo_secret_{user['id']}".encode()).hexdigest()
                cur.execute(
                    """
                    INSERT INTO users (id, email, password_hash, display_name, status, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        display_name = EXCLUDED.display_name,
                        status = EXCLUDED.status,
                        updated_at = EXCLUDED.updated_at;
                    """,
                    (user["id"], user["email"], dummy_pwd_hash, user["display_name"], user["status"], now, now),
                )

            # 3. Insert Subscriptions
            for user in DEMO_USERS:
                cur.execute(
                    """
                    INSERT INTO subscriptions (
                        id, user_id, plan_id, status, starts_at,
                        current_period_start, current_period_end, cancel_at_period_end, created_at
                    )
                    VALUES (%s, %s, %s, 'active', %s, %s, %s, FALSE, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        status = 'active',
                        current_period_end = EXCLUDED.current_period_end;
                    """,
                    (user["sub_id"], user["id"], user["plan_id"], now, now, period_end, now),
                )

            # 4. Insert API Keys (Only generate new key if key does not already exist)
            for user in DEMO_USERS:
                cur.execute("SELECT id, key_prefix FROM api_keys WHERE id = %s;", (user["key_id"],))
                existing_key = cur.fetchone()
                
                if existing_key:
                    generated_keys_output.append({
                        "user": user["display_name"],
                        "email": user["email"],
                        "key_name": user["key_name"],
                        "key_prefix": existing_key[1],
                        "plaintext_key": "[ALREADY CREATED - SECRETS ARE NOT RE-DISPLAYED]",
                        "status": "Existing",
                    })
                else:
                    plaintext_key, prefix, key_hash = generate_secure_api_key()
                    cur.execute(
                        """
                        INSERT INTO api_keys (
                            id, user_id, name, key_prefix, key_hash, created_at, expires_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s);
                        """,
                        (user["key_id"], user["id"], user["key_name"], prefix, key_hash, now, expires_at),
                    )
                    generated_keys_output.append({
                        "user": user["display_name"],
                        "email": user["email"],
                        "key_name": user["key_name"],
                        "key_prefix": prefix,
                        "plaintext_key": plaintext_key,
                        "status": "Created",
                    })

    return {
        "users_count": len(DEMO_USERS),
        "keys_output": generated_keys_output,
    }


def validate_database_integrity(conn: psycopg.Connection) -> Dict[str, Any]:
    """
    Validates that:
    1. All 3 demo users exist.
    2. Each user has an active subscription linked to a valid plan.
    3. Each user has an API key with valid hash format.
    4. No plaintext keys are stored.
    """
    results: Dict[str, Any] = {"passed": True, "checks": []}
    
    with conn.cursor(row_factory=dict_row) as cur:
        # Check users
        cur.execute(
            """
            SELECT id, email, display_name, status
            FROM users
            WHERE id IN (%s, %s, %s);
            """,
            tuple(u["id"] for u in DEMO_USERS),
        )
        users = cur.fetchall()
        user_check = len(users) == 3
        results["checks"].append({
            "name": "3 Demo Users Exist",
            "passed": user_check,
            "details": f"Found {len(users)} of 3 demo users.",
        })
        if not user_check:
            results["passed"] = False

        # Check API keys
        cur.execute(
            """
            SELECT id, user_id, name, key_prefix, key_hash, expires_at
            FROM api_keys
            WHERE user_id IN (%s, %s, %s);
            """,
            tuple(u["id"] for u in DEMO_USERS),
        )
        keys = cur.fetchall()
        keys_check = len(keys) == 3
        results["checks"].append({
            "name": "3 Demo API Keys Exist",
            "passed": keys_check,
            "details": f"Found {len(keys)} of 3 keys.",
        })
        if not keys_check:
            results["passed"] = False

        # Check hash format and ensure no plaintext keys are stored
        all_hashes_valid = True
        no_plaintext = True
        for k in keys:
            kh = k["key_hash"].strip()
            if len(kh) != 64 or not all(c in "0123456789abcdef" for c in kh):
                all_hashes_valid = False
            if "mf_live_" in kh:
                no_plaintext = False

        results["checks"].append({
            "name": "API Key Hashes Format (64-char lowercase hex)",
            "passed": all_hashes_valid,
            "details": "All key hashes conform to ^[0-9a-f]{64}$ constraint." if all_hashes_valid else "Invalid hash format detected!",
        })
        results["checks"].append({
            "name": "No Plaintext API Keys in Database",
            "passed": no_plaintext,
            "details": "Zero plaintext secrets stored in DB." if no_plaintext else "CRITICAL: Plaintext secret found in DB!",
        })
        if not all_hashes_valid or not no_plaintext:
            results["passed"] = False

        # Check Subscriptions
        cur.execute(
            """
            SELECT s.id, s.user_id, s.plan_id, s.status, p.code AS plan_code
            FROM subscriptions s
            JOIN subscription_plans p ON s.plan_id = p.id
            WHERE s.user_id IN (%s, %s, %s);
            """,
            tuple(u["id"] for u in DEMO_USERS),
        )
        subs = cur.fetchall()
        subs_check = len(subs) == 3
        results["checks"].append({
            "name": "3 Demo Subscriptions Linked to Valid Plans",
            "passed": subs_check,
            "details": f"Found {len(subs)} valid subscriptions ({', '.join(s['plan_code'] for s in subs)}).",
        })
        if not subs_check:
            results["passed"] = False

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Create MeterFlow demo users and API keys.")
    parser.add_argument("--dry-run", action="store_true", help="Generate credentials and validate logic without connecting to DB.")
    args = parser.parse_args()

    print("=" * 70)
    print(" MeterFlow — Step 3: Demo Users and API Keys Generator (Python)")
    print("=" * 70)
    print(f"Target Database URL: {DATABASE_URL}")

    if args.dry_run:
        print("\n[i] DRY-RUN MODE: Simulating generation and verifying cryptographic rules...")
        for user in DEMO_USERS:
            plaintext_key, prefix, key_hash = generate_secure_api_key()
            print("-" * 70)
            print(f"User:        {user['display_name']} ({user['email']})")
            print(f"Plan ID:     {user['plan_id']} ({user['plan_code'].upper()})")
            print(f"Key Name:    {user['key_name']}")
            print(f"Key Prefix:  {prefix}")
            print(f"Secret Key:  {plaintext_key}")
            print(f"Key Hash:    {key_hash}")
            print(f"Hash Valid:  {len(key_hash) == 64 and key_hash == hashlib.sha256(plaintext_key.encode()).hexdigest()}")
        print("-" * 70)
        print("[✓] Dry-run cryptographic and schema validation completed successfully.")
        return

    # Check connection
    try:
        # 3 seconds timeout to prevent long hangs if PostgreSQL is offline
        conn = psycopg.connect(DATABASE_URL, autocommit=False, connect_timeout=3)
    except Exception as exc:
        print("\n[!] Connection Error: Could not connect to PostgreSQL.")
        print(f"    Details: {exc}")
        print("\nPossible reasons:")
        print("  1. PostgreSQL service is not currently running on port 5432.")
        print("  2. DATABASE_URL in .env has invalid credentials or host.")
        print("\nTo configure your connection, create or edit .env in project root:")
        print("  DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<dbname>")
        sys.exit(1)

    try:
        print("\n[+] Creating / Updating demo users and credentials...")
        result = create_demo_data(conn)
        print(f"[✓] Processed {result['users_count']} demo users successfully.")

        print("\n" + "-" * 70)
        print(" DEMO API KEYS (DISPLAYED ONCE AT CREATION)")
        print("-" * 70)
        for k in result["keys_output"]:
            print(f"User:        {k['user']} ({k['email']})")
            print(f"Key Name:    {k['key_name']}")
            print(f"Key Prefix:  {k['key_prefix']}")
            print(f"Secret Key:  {k['plaintext_key']}")
            print(f"Status:      {k['status']}")
            print("-" * 70)

        print("\n[+] Running Database Integrity Validation...")
        val_report = validate_database_integrity(conn)
        for check in val_report["checks"]:
            mark = "[PASS]" if check["passed"] else "[FAIL]"
            print(f"  {mark} {check['name']}: {check['details']}")

        if val_report["passed"]:
            print("\n[✓] ALL INTEGRITY CHECKS PASSED SUCCESSFULLY.")
        else:
            print("\n[✗] ONE OR MORE INTEGRITY CHECKS FAILED.")
            sys.exit(2)

    except Exception as exc:
        conn.rollback()
        print(f"\n[!] Error during execution (transaction rolled back): {exc}")
        raise exc
    finally:
        conn.close()


if __name__ == "__main__":
    main()
