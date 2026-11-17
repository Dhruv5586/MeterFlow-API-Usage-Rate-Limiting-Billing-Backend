#!/usr/bin/env python3
"""
MeterFlow — Daily Usage Aggregation Rollup Worker
-------------------------------------------------
Aggregates granular 'usage_events' into dimensional 'usage_daily' summaries.
Can be executed as a nightly background cron task or on-demand.
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, date

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.core.database import SessionLocal
from app.services.aggregation_service import AggregationService


def main():
    parser = argparse.ArgumentParser(description="MeterFlow Daily Usage Aggregation Worker")
    parser.add_argument("--date", type=str, default=None, help="Specific date to aggregate (YYYY-MM-DD). Defaults to all dates.")
    parser.add_argument("--subscription-id", type=str, default=None, help="Filter by specific subscription UUID.")
    args = parser.parse_args()

    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"[!] Error: Invalid date format '{args.date}'. Expected YYYY-MM-DD.")
            sys.exit(1)

    print("=" * 70)
    print("       METERFLOW BACKGROUND ROLLUP WORKER: USAGE_EVENTS -> USAGE_DAILY")
    print("=" * 70)
    print(f"Target Date: {target_date or 'ALL HISTORICAL DATES'}")
    if args.subscription_id:
        print(f"Filter Subscription: {args.subscription_id}")
    print()

    db = SessionLocal()
    try:
        service = AggregationService(db)
        stats = service.rollup_daily_usage(target_date=target_date, subscription_id=args.subscription_id)

        print("[✓] Aggregation Succeeded!")
        print(f"    • Dimensional Rows Upserted: {stats['rows_affected']:,}")
        print(f"    • Total Requests Aggregated: {stats['total_requests_aggregated']:,}")
        print(f"    • Data Volume Transferred:   {stats['total_bytes_aggregated'] / (1024*1024):.2f} MB")
        print(f"    • Distinct Calendar Days:    {stats['days_covered']}")
        print(f"    • Execution Time:            {stats['execution_time_ms']} ms")
        print("=" * 70)
    except Exception as exc:
        print(f"[✗] Aggregation Failed: {exc}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
