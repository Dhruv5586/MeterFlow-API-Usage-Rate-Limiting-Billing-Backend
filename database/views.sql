BEGIN;

CREATE OR REPLACE VIEW daily_api_usage AS
SELECT
    usage_date,
    user_id,
    subscription_id,
    api_key_id,
    endpoint,
    http_method,
    request_count,
    successful_request_count,
    error_request_count,
    response_bytes,
    latency_sum_ms,
    CASE
        WHEN request_count = 0 THEN NULL
        ELSE latency_sum_ms::NUMERIC / request_count
    END AS average_latency_ms
FROM usage_daily;

-- Totals cover all recorded daily summaries for each subscription, not just
-- the current billing period. Use daily_api_usage with an explicit date range
-- for period-specific reporting.
CREATE OR REPLACE VIEW subscription_usage_summary AS
SELECT
    subscriptions.id AS subscription_id,
    subscriptions.user_id,
    subscription_plans.code AS plan_code,
    subscriptions.status AS subscription_status,
    COALESCE(SUM(usage_daily.request_count), 0)::BIGINT AS total_requests,
    COALESCE(SUM(usage_daily.successful_request_count), 0)::BIGINT
        AS successful_requests,
    COALESCE(SUM(usage_daily.error_request_count), 0)::BIGINT AS error_requests,
    COALESCE(SUM(usage_daily.response_bytes), 0)::BIGINT AS total_response_bytes,
    CASE
        WHEN COALESCE(SUM(usage_daily.request_count), 0) = 0 THEN NULL
        ELSE SUM(usage_daily.latency_sum_ms)::NUMERIC
            / SUM(usage_daily.request_count)
    END AS average_latency_ms,
    MAX(usage_daily.usage_date) AS last_usage_date
FROM subscriptions
JOIN subscription_plans
    ON subscription_plans.id = subscriptions.plan_id
LEFT JOIN usage_daily
    ON usage_daily.subscription_id = subscriptions.id
GROUP BY
    subscriptions.id,
    subscriptions.user_id,
    subscription_plans.code,
    subscriptions.status;

COMMIT;
