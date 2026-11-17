#!/usr/bin/env python3
"""
MeterFlow — Step 4: Transform Dataset
-------------------------------------
Reads data/raw/access_logs.csv, cleans and classifies routes, filters approved
API requests only, strips query strings, normalizes types, and deterministically
maps records to valid demo users and API keys.

Outputs:
- data/processed/api_usage_events.csv
"""

import os
import sys
import uuid
import re
from pathlib import Path
from urllib.parse import urlparse
import pandas as pd
from datetime import datetime, timezone

# Demo User Mappings (established in Step 3)
DEMO_TENANTS = [
    {
        "user_id": "20000000-0000-4000-8000-000000000001",
        "api_key_id": "40000000-0000-4000-8000-000000000001",
        "subscription_id": "30000000-0000-4000-8000-000000000001",
        "name": "TechNova Solutions",
    },
    {
        "user_id": "20000000-0000-4000-8000-000000000002",
        "api_key_id": "40000000-0000-4000-8000-000000000002",
        "subscription_id": "30000000-0000-4000-8000-000000000002",
        "name": "CloudSphere Technologies",
    },
    {
        "user_id": "20000000-0000-4000-8000-000000000003",
        "api_key_id": "40000000-0000-4000-8000-000000000003",
        "subscription_id": "30000000-0000-4000-8000-000000000003",
        "name": "DataBridge Systems",
    },
]

KNOWN_WEBSITE_ROUTES = {
    "/about", "/contact", "/pricing", "/login", "/register",
    "/blog", "/blog/{slug}", "/docs", "/docs/{page}", "/",
    "/.well-known/security.txt", "/healthz"
}


def classify_route(path: str) -> str:
    """
    Classifies a URL path into 'api', 'static', 'website', or 'unknown'.
    """
    clean_path = path.split("?")[0].strip()
    
    # 1. API Endpoints
    if clean_path.startswith("/api/"):
        return "api"
    
    # 2. Static Assets
    if (
        clean_path.startswith("/static/")
        or clean_path.endswith((".ico", ".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".txt", ".xml"))
    ):
        return "static"
    
    # 3. Known Website Pages
    if clean_path in KNOWN_WEBSITE_ROUTES:
        return "website"
    
    return "unknown"


def clean_endpoint(raw_path: str) -> str:
    """
    Removes query strings, strips whitespace, and ensures leading slash.
    """
    if not isinstance(raw_path, str):
        return "/"
    # Parse URL and retain only the clean path
    parsed = urlparse(raw_path)
    path = parsed.path.strip()
    if not path.startswith("/"):
        path = f"/{path}"
    return path


def transform():
    root_dir = Path(__file__).resolve().parent.parent
    raw_csv_path = root_dir / "data" / "raw" / "access_logs.csv"
    processed_dir = root_dir / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    processed_csv_path = processed_dir / "api_usage_events.csv"

    print("=" * 70)
    print(" MeterFlow — Step 4: Dataset Transformation (Pandas)")
    print("=" * 70)
    print(f"Reading raw dataset: {raw_csv_path}")

    if not raw_csv_path.exists():
        print(f"[!] Error: Raw dataset file {raw_csv_path} not found.")
        sys.exit(1)

    # Read original CSV without altering it
    df = pd.read_csv(raw_csv_path)
    total_source_records = len(df)
    print(f"[+] Total raw records loaded: {total_source_records}")

    # Track classification counts
    classification_counts = {"api": 0, "static": 0, "website": 0, "unknown": 0, "invalid": 0}

    transformed_rows = []

    for idx, row in df.iterrows():
        source_record_id = idx + 1  # 1-indexed source row ID
        raw_path = str(row.get("path", ""))
        
        category = classify_route(raw_path)
        if category in classification_counts:
            classification_counts[category] += 1
        else:
            classification_counts["unknown"] += 1

        # Only process approved API requests
        if category != "api":
            continue

        # Data Validation
        try:
            # 1. Clean endpoint path (no query strings)
            endpoint = clean_endpoint(raw_path)

            # 2. HTTP method
            http_method = str(row.get("method", "")).strip().upper()
            if http_method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                classification_counts["invalid"] += 1
                continue

            # 3. Status code
            status_code = int(row.get("status_code", 0))
            if not (100 <= status_code <= 599):
                classification_counts["invalid"] += 1
                continue

            # 4. Latency
            latency_ms = int(row.get("response_time_ms", 0))
            if latency_ms < 0:
                classification_counts["invalid"] += 1
                continue

            # 5. Response size
            response_size_bytes = int(row.get("bytes_sent", 0))
            if response_size_bytes < 0:
                classification_counts["invalid"] += 1
                continue

            # 6. Timestamp -> UTC ISO-8601 string
            raw_ts = str(row.get("timestamp", "")).strip()
            # Raw format: 2024-01-01 00:15:12
            dt = datetime.strptime(raw_ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            created_at = dt.isoformat()

            # 7. Source server ID
            source_server_id = str(row.get("server_id", "")).strip()

            # 8. Deterministic Tenant Allocation
            # Balances events cleanly across the 3 demo users
            tenant = DEMO_TENANTS[idx % len(DEMO_TENANTS)]
            user_id = tenant["user_id"]
            api_key_id = tenant["api_key_id"]
            subscription_id = tenant["subscription_id"]

            # Unique key for database deduplication
            source_record_key = f"access_logs_csv:{source_record_id}"

            transformed_rows.append({
                "source_record_id": source_record_id,
                "source_record_key": source_record_key,
                "source_dataset": "web-server-logs",
                "user_id": user_id,
                "api_key_id": api_key_id,
                "subscription_id": subscription_id,
                "http_method": http_method,
                "endpoint": endpoint,
                "status_code": status_code,
                "latency_ms": latency_ms,
                "response_size_bytes": response_size_bytes,
                "source_server_id": source_server_id,
                "created_at": created_at,
            })

        except Exception as exc:
            classification_counts["invalid"] += 1
            continue

    # Convert to DataFrame and save
    out_df = pd.DataFrame(transformed_rows)
    out_df.to_csv(processed_csv_path, index=False)

    print("\n" + "-" * 70)
    print(" TRANSFORMATION SUMMARY")
    print("-" * 70)
    print(f"Total Source Records:          {total_source_records}")
    print(f"Approved API Records:          {classification_counts['api']}")
    print(f"Excluded Static Assets:        {classification_counts['static']}")
    print(f"Excluded Website Routes:       {classification_counts['website']}")
    print(f"Unknown Routes:                {classification_counts['unknown']}")
    print(f"Invalid / Dropped Records:     {classification_counts['invalid']}")
    print(f"Cleaned Records Saved:         {len(out_df)}")
    print(f"Output File:                   {processed_csv_path}")
    print("-" * 70)
    print("[✓] Transformation completed successfully.")


if __name__ == "__main__":
    transform()
