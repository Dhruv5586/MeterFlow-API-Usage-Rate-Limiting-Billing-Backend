#!/usr/bin/env python3
"""
MeterFlow — Apply Phase 6 Payment Schema
----------------------------------------
Safely creates 'payments' and 'payment_webhook_events' tables
without touching any existing tables or rows.
"""

import sys
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import text
from app.core.database import engine, Base
from app.models.payment import Payment, PaymentWebhookEvent


def main():
    print("=" * 60)
    print(" MeterFlow — Applying Phase 6 Payments Schema")
    print("=" * 60)

    sql_file = ROOT_DIR / "database" / "payments_schema.sql"
    sql_content = sql_file.read_text(encoding="utf-8")

    with engine.begin() as conn:
        print("[+] Executing payments_schema.sql...")
        conn.execute(text(sql_content))
        print("[✓] Payments tables & indexes created successfully!")

    print("=" * 60)


if __name__ == "__main__":
    main()
