"""
Daily Usage Aggregation & Rollup Service
----------------------------------------
Aggregates granular, high-volume records from 'usage_events' into 'usage_daily'
broken down by dimensional tuples:
(usage_date, subscription_id, api_key_id, endpoint, http_method)

Fully idempotent: uses ON CONFLICT DO UPDATE to ensure repeated runs or backfills
accurately update daily sums without duplicating data.
"""

import logging
from datetime import date, datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger("meterflow.aggregation")


class AggregationService:
    def __init__(self, db: Session):
        self.db = db

    def rollup_daily_usage(
        self,
        target_date: Optional[date] = None,
        subscription_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes daily rollups from 'usage_events' into 'usage_daily'.
        
        If target_date is provided, only processes events on that date.
        If target_date is None, processes all unaggregated or existing events across all dates.
        """
        start_time = datetime.now(timezone.utc)
        
        where_clauses = ["1=1"]
        params: Dict[str, Any] = {}

        if target_date:
            where_clauses.append("DATE(created_at) = :target_date")
            params["target_date"] = target_date
        
        if subscription_id:
            where_clauses.append("subscription_id = :subscription_id")
            params["subscription_id"] = subscription_id

        where_sql = " AND ".join(where_clauses)

        rollup_sql = text(f"""
            INSERT INTO usage_daily (
                id,
                user_id,
                subscription_id,
                api_key_id,
                usage_date,
                endpoint,
                http_method,
                request_count,
                successful_request_count,
                error_request_count,
                response_bytes,
                latency_sum_ms,
                updated_at
            )
            SELECT 
                gen_random_uuid() AS id,
                user_id,
                subscription_id,
                api_key_id,
                DATE(created_at) AS usage_date,
                endpoint,
                http_method,
                COUNT(*) AS request_count,
                COUNT(CASE WHEN status_code < 400 THEN 1 END) AS successful_request_count,
                COUNT(CASE WHEN status_code >= 400 THEN 1 END) AS error_request_count,
                SUM(response_size_bytes) AS response_bytes,
                SUM(latency_ms) AS latency_sum_ms,
                CURRENT_TIMESTAMP AS updated_at
            FROM usage_events
            WHERE {where_sql}
            GROUP BY 
                user_id,
                subscription_id,
                api_key_id,
                DATE(created_at),
                endpoint,
                http_method
            ON CONFLICT (usage_date, subscription_id, api_key_id, endpoint, http_method)
            DO UPDATE SET
                request_count = EXCLUDED.request_count,
                successful_request_count = EXCLUDED.successful_request_count,
                error_request_count = EXCLUDED.error_request_count,
                response_bytes = EXCLUDED.response_bytes,
                latency_sum_ms = EXCLUDED.latency_sum_ms,
                updated_at = CURRENT_TIMESTAMP;
        """)

        result = self.db.execute(rollup_sql, params)
        self.db.commit()

        # Query summary of aggregated records
        summary_query = text(f"""
            SELECT 
                COUNT(*) AS total_daily_rows,
                COALESCE(SUM(request_count), 0) AS total_requests,
                COALESCE(SUM(response_bytes), 0) AS total_bytes,
                COALESCE(COUNT(DISTINCT usage_date), 0) AS days_covered
            FROM usage_daily
            {"WHERE usage_date = :target_date" if target_date else ""};
        """)
        summary_params = {"target_date": target_date} if target_date else {}
        summary_row = self.db.execute(summary_query, summary_params).fetchone()

        elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        stats = {
            "rows_affected": result.rowcount,
            "total_daily_rows": summary_row.total_daily_rows if summary_row else 0,
            "total_requests_aggregated": summary_row.total_requests if summary_row else 0,
            "total_bytes_aggregated": summary_row.total_bytes if summary_row else 0,
            "days_covered": summary_row.days_covered if summary_row else 0,
            "execution_time_ms": elapsed_ms,
            "target_date": str(target_date) if target_date else "all_dates",
        }

        logger.info(f"Daily aggregation completed: {stats}")
        return stats
