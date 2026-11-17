BEGIN;

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT users_email_normalized_ck
        CHECK (email <> '' AND email = LOWER(email)),
    CONSTRAINT users_password_hash_nonempty_ck
        CHECK (password_hash <> ''),
    CONSTRAINT users_display_name_nonempty_ck
        CHECK (BTRIM(display_name) <> ''),
    CONSTRAINT users_status_ck
        CHECK (status IN ('active', 'suspended', 'closed'))
);

CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    name TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    key_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    CONSTRAINT api_keys_user_fk
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT api_keys_user_id_id_uq UNIQUE (user_id, id),
    CONSTRAINT api_keys_name_nonempty_ck
        CHECK (BTRIM(name) <> ''),
    CONSTRAINT api_keys_prefix_nonempty_ck
        CHECK (BTRIM(key_prefix) <> ''),
    CONSTRAINT api_keys_hash_format_ck
        CHECK (key_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT api_keys_expiry_after_creation_ck
        CHECK (expires_at IS NULL OR expires_at > created_at),
    CONSTRAINT api_keys_revocation_after_creation_ck
        CHECK (revoked_at IS NULL OR revoked_at >= created_at)
);

CREATE TABLE subscription_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    billing_interval TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT subscription_plans_code_nonempty_ck
        CHECK (BTRIM(code) <> ''),
    CONSTRAINT subscription_plans_name_nonempty_ck
        CHECK (BTRIM(name) <> ''),
    CONSTRAINT subscription_plans_price_nonnegative_ck
        CHECK (price >= 0),
    CONSTRAINT subscription_plans_currency_format_ck
        CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT subscription_plans_interval_ck
        CHECK (billing_interval IN ('month', 'year'))
);

CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    plan_id UUID NOT NULL,
    status TEXT NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    current_period_start TIMESTAMPTZ NOT NULL,
    current_period_end TIMESTAMPTZ NOT NULL,
    canceled_at TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT subscriptions_user_fk
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT subscriptions_plan_fk
        FOREIGN KEY (plan_id) REFERENCES subscription_plans (id) ON DELETE RESTRICT,
    CONSTRAINT subscriptions_user_id_id_uq UNIQUE (user_id, id),
    CONSTRAINT subscriptions_status_ck
        CHECK (status IN ('trialing', 'active', 'past_due', 'canceled', 'ended')),
    CONSTRAINT subscriptions_period_ck
        CHECK (current_period_end > current_period_start)
);

CREATE TABLE usage_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    api_key_id UUID NOT NULL,
    subscription_id UUID NOT NULL,
    http_method TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    status_code SMALLINT NOT NULL,
    latency_ms INTEGER NOT NULL,
    response_size_bytes BIGINT NOT NULL,
    source_server_id TEXT,
    source_record_key TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT usage_events_user_fk
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT usage_events_user_api_key_fk
        FOREIGN KEY (user_id, api_key_id)
        REFERENCES api_keys (user_id, id) ON DELETE RESTRICT,
    CONSTRAINT usage_events_user_subscription_fk
        FOREIGN KEY (user_id, subscription_id)
        REFERENCES subscriptions (user_id, id) ON DELETE RESTRICT,
    CONSTRAINT usage_events_method_ck
        CHECK (http_method IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS')),
    CONSTRAINT usage_events_endpoint_ck
        CHECK (
            BTRIM(endpoint) <> ''
            AND LEFT(endpoint, 1) = '/'
            AND POSITION('?' IN endpoint) = 0
        ),
    CONSTRAINT usage_events_status_code_ck
        CHECK (status_code BETWEEN 100 AND 599),
    CONSTRAINT usage_events_latency_nonnegative_ck
        CHECK (latency_ms >= 0),
    CONSTRAINT usage_events_response_size_nonnegative_ck
        CHECK (response_size_bytes >= 0),
    CONSTRAINT usage_events_source_record_key_nonempty_ck
        CHECK (source_record_key IS NULL OR BTRIM(source_record_key) <> '')
);

CREATE TABLE usage_daily (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    subscription_id UUID NOT NULL,
    api_key_id UUID NOT NULL,
    usage_date DATE NOT NULL,
    endpoint TEXT NOT NULL,
    http_method TEXT NOT NULL,
    request_count BIGINT NOT NULL,
    successful_request_count BIGINT NOT NULL DEFAULT 0,
    error_request_count BIGINT NOT NULL DEFAULT 0,
    response_bytes BIGINT NOT NULL DEFAULT 0,
    latency_sum_ms BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT usage_daily_user_fk
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT usage_daily_user_subscription_fk
        FOREIGN KEY (user_id, subscription_id)
        REFERENCES subscriptions (user_id, id) ON DELETE RESTRICT,
    CONSTRAINT usage_daily_user_api_key_fk
        FOREIGN KEY (user_id, api_key_id)
        REFERENCES api_keys (user_id, id) ON DELETE RESTRICT,
    CONSTRAINT usage_daily_dimensions_uq
        UNIQUE (usage_date, subscription_id, api_key_id, endpoint, http_method),
    CONSTRAINT usage_daily_method_ck
        CHECK (http_method IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS')),
    CONSTRAINT usage_daily_endpoint_ck
        CHECK (BTRIM(endpoint) <> '' AND LEFT(endpoint, 1) = '/' AND POSITION('?' IN endpoint) = 0),
    CONSTRAINT usage_daily_request_count_nonnegative_ck
        CHECK (request_count >= 0),
    CONSTRAINT usage_daily_success_count_nonnegative_ck
        CHECK (successful_request_count >= 0),
    CONSTRAINT usage_daily_error_count_nonnegative_ck
        CHECK (error_request_count >= 0),
    CONSTRAINT usage_daily_outcome_counts_ck
        CHECK (successful_request_count + error_request_count <= request_count),
    CONSTRAINT usage_daily_response_bytes_nonnegative_ck
        CHECK (response_bytes >= 0),
    CONSTRAINT usage_daily_latency_nonnegative_ck
        CHECK (latency_sum_ms >= 0)
);

CREATE TABLE usage_quotas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id UUID NOT NULL,
    metric TEXT NOT NULL,
    period TEXT NOT NULL,
    quota_limit BIGINT NOT NULL,
    is_hard_limit BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT usage_quotas_subscription_fk
        FOREIGN KEY (subscription_id) REFERENCES subscriptions (id) ON DELETE RESTRICT,
    CONSTRAINT usage_quotas_dimensions_uq UNIQUE (subscription_id, metric, period),
    CONSTRAINT usage_quotas_metric_nonempty_ck
        CHECK (BTRIM(metric) <> ''),
    CONSTRAINT usage_quotas_period_ck
        CHECK (period IN ('day', 'month')),
    CONSTRAINT usage_quotas_limit_nonnegative_ck
        CHECK (quota_limit >= 0)
);

CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    subscription_id UUID NOT NULL,
    invoice_number TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    currency CHAR(3) NOT NULL,
    subtotal NUMERIC(12, 2) NOT NULL,
    tax NUMERIC(12, 2) NOT NULL,
    total NUMERIC(12, 2) NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    due_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT invoices_user_fk
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT invoices_user_subscription_fk
        FOREIGN KEY (user_id, subscription_id)
        REFERENCES subscriptions (user_id, id) ON DELETE RESTRICT,
    CONSTRAINT invoices_number_nonempty_ck
        CHECK (BTRIM(invoice_number) <> ''),
    CONSTRAINT invoices_status_ck
        CHECK (status IN ('draft', 'open', 'paid', 'void', 'uncollectible')),
    CONSTRAINT invoices_currency_format_ck
        CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT invoices_subtotal_nonnegative_ck
        CHECK (subtotal >= 0),
    CONSTRAINT invoices_tax_nonnegative_ck
        CHECK (tax >= 0),
    CONSTRAINT invoices_total_nonnegative_ck
        CHECK (total >= 0),
    CONSTRAINT invoices_due_after_issued_ck
        CHECK (due_at IS NULL OR due_at >= issued_at)
);

CREATE TABLE invoice_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID NOT NULL,
    description TEXT NOT NULL,
    quantity NUMERIC(14, 4) NOT NULL,
    unit_price NUMERIC(12, 4) NOT NULL,
    line_amount NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT invoice_items_invoice_fk
        FOREIGN KEY (invoice_id) REFERENCES invoices (id) ON DELETE CASCADE,
    CONSTRAINT invoice_items_description_nonempty_ck
        CHECK (BTRIM(description) <> ''),
    CONSTRAINT invoice_items_quantity_nonnegative_ck
        CHECK (quantity >= 0),
    CONSTRAINT invoice_items_unit_price_nonnegative_ck
        CHECK (unit_price >= 0),
    CONSTRAINT invoice_items_amount_nonnegative_ck
        CHECK (line_amount >= 0)
);

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID,
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT audit_logs_actor_user_fk
        FOREIGN KEY (actor_user_id) REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT audit_logs_action_nonempty_ck
        CHECK (BTRIM(action) <> ''),
    CONSTRAINT audit_logs_entity_type_nonempty_ck
        CHECK (BTRIM(entity_type) <> ''),
    CONSTRAINT audit_logs_details_object_ck
        CHECK (JSONB_TYPEOF(details) = 'object')
);

COMMIT;
