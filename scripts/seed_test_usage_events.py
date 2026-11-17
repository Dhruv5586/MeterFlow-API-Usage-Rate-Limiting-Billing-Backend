"""
Seed baseline usage events into neondb_test from data/processed/api_usage_events.csv
"""
import sys
import uuid
from pathlib import Path
import pandas as pd
from sqlalchemy import text

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from tests.conftest import test_engine

def seed_usage_events():
    csv_path = root_dir / "data" / "processed" / "api_usage_events.csv"
    if not csv_path.exists():
        print("CSV not found:", csv_path)
        return

    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} rows from {csv_path}")

    with test_engine.begin() as conn:
        # Ensure default gen_random_uuid() is set
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))
        conn.execute(text("ALTER TABLE usage_events ALTER COLUMN id SET DEFAULT gen_random_uuid();"))

        insert_sql = text("""
            INSERT INTO usage_events (
                id, user_id, api_key_id, subscription_id, http_method,
                endpoint, status_code, latency_ms, response_size_bytes,
                source_server_id, source_record_key, created_at
            )
            VALUES (
                :id, :user_id, :api_key_id, :subscription_id, :http_method,
                :endpoint, :status_code, :latency_ms, :response_size_bytes,
                :source_server_id, :source_record_key, :created_at
            )
            ON CONFLICT (source_record_key) DO NOTHING;
        """)

        records = []
        for _, row in df.iterrows():
            records.append({
                "id": str(uuid.uuid4()),
                "user_id": str(row["user_id"]),
                "api_key_id": str(row["api_key_id"]),
                "subscription_id": str(row["subscription_id"]),
                "http_method": str(row["http_method"]),
                "endpoint": str(row["endpoint"]),
                "status_code": int(row["status_code"]),
                "latency_ms": int(row["latency_ms"]),
                "response_size_bytes": int(row["response_size_bytes"]),
                "source_server_id": str(row["source_server_id"]),
                "source_record_key": str(row["source_record_key"]),
                "created_at": str(row["created_at"]),
            })

        count_before = conn.execute(text("SELECT count(*) FROM usage_events")).scalar()
        print(f"usage_events count before: {count_before}")

        batch_size = 500
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            conn.execute(insert_sql, batch)

        count_after = conn.execute(text("SELECT count(*) FROM usage_events")).scalar()
        print(f"usage_events count after: {count_after}")

if __name__ == "__main__":
    seed_usage_events()
