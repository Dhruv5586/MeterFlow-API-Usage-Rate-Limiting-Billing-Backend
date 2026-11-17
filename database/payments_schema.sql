-- Phase 6: Payments and Webhook Idempotency Tables
BEGIN;

CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    invoice_id UUID NOT NULL,
    razorpay_order_id TEXT NOT NULL,
    razorpay_payment_id TEXT UNIQUE,
    razorpay_signature TEXT,
    amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL DEFAULT 'created',
    method TEXT,
    error_code TEXT,
    error_description TEXT,
    captured_at TIMESTAMPTZ,
    refunded_at TIMESTAMPTZ,
    amount_refunded NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT payments_user_fk
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT payments_invoice_fk
        FOREIGN KEY (invoice_id) REFERENCES invoices (id) ON DELETE RESTRICT,
    CONSTRAINT payments_status_ck
        CHECK (status IN ('created', 'authorized', 'captured', 'failed', 'refunded')),
    CONSTRAINT payments_amount_nonnegative_ck
        CHECK (amount >= 0),
    CONSTRAINT payments_refund_nonnegative_ck
        CHECK (amount_refunded >= 0)
);

CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments (user_id);
CREATE INDEX IF NOT EXISTS idx_payments_invoice_id ON payments (invoice_id);
CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments (razorpay_order_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments (status);

CREATE TABLE IF NOT EXISTS payment_webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    order_id TEXT,
    payment_id TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    status TEXT NOT NULL DEFAULT 'processed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT webhook_events_status_ck
        CHECK (status IN ('processed', 'ignored', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_payment_webhook_events_order_id ON payment_webhook_events (order_id);
CREATE INDEX IF NOT EXISTS idx_payment_webhook_events_payment_id ON payment_webhook_events (payment_id);
CREATE INDEX IF NOT EXISTS idx_payment_webhook_events_type ON payment_webhook_events (event_type);

COMMIT;
