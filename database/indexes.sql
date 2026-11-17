BEGIN;

-- User key-management screens list keys newest first.
CREATE INDEX IF NOT EXISTS api_keys_user_created_at_idx
    ON api_keys (user_id, created_at DESC);

-- Enforces one current subscription per developer while keeping subscription history.
CREATE UNIQUE INDEX IF NOT EXISTS subscriptions_one_current_per_user_uq
    ON subscriptions (user_id)
    WHERE status IN ('trialing', 'active', 'past_due');

-- A developer's subscription history is commonly read newest first.
CREATE INDEX IF NOT EXISTS subscriptions_user_created_at_idx
    ON subscriptions (user_id, created_at DESC);

-- Supports recent usage queries scoped to a developer.
CREATE INDEX IF NOT EXISTS usage_events_user_created_at_idx
    ON usage_events (user_id, created_at DESC);

-- Supports recent usage queries and usage windows scoped to an API key.
CREATE INDEX IF NOT EXISTS usage_events_api_key_created_at_idx
    ON usage_events (api_key_id, created_at DESC);

-- Supports billing/usage queries scoped to a subscription and event-time range.
CREATE INDEX IF NOT EXISTS usage_events_subscription_created_at_idx
    ON usage_events (subscription_id, created_at DESC);

-- The unique aggregate index starts with usage_date; this supports subscription-first lookups.
CREATE INDEX IF NOT EXISTS usage_daily_subscription_date_idx
    ON usage_daily (subscription_id, usage_date DESC);

-- Supports daily history queries for an individual API key.
CREATE INDEX IF NOT EXISTS usage_daily_api_key_date_idx
    ON usage_daily (api_key_id, usage_date DESC);

-- Supports invoice history screens for a developer.
CREATE INDEX IF NOT EXISTS invoices_user_issued_at_idx
    ON invoices (user_id, issued_at DESC);

-- Supports billing-period and invoice lookups for a subscription.
CREATE INDEX IF NOT EXISTS invoices_subscription_issued_at_idx
    ON invoices (subscription_id, issued_at DESC);

-- Supports loading all lines when an invoice is opened or removed as a draft.
CREATE INDEX IF NOT EXISTS invoice_items_invoice_id_idx
    ON invoice_items (invoice_id);

-- Supports an actor's audit history in reverse chronological order.
CREATE INDEX IF NOT EXISTS audit_logs_actor_occurred_at_idx
    ON audit_logs (actor_user_id, occurred_at DESC)
    WHERE actor_user_id IS NOT NULL;

COMMIT;
