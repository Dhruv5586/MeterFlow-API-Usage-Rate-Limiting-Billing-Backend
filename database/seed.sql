BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

INSERT INTO subscription_plans (
    id,
    code,
    name,
    price,
    currency,
    billing_interval,
    is_active
)
VALUES
    ('00000000-0000-4000-8000-000000000001', 'free', 'Free', 0.00, 'USD', 'month', TRUE),
    ('00000000-0000-4000-8000-000000000002', 'pro', 'Pro', 29.00, 'USD', 'month', TRUE),
    ('00000000-0000-4000-8000-000000000003', 'enterprise', 'Enterprise', 299.00, 'USD', 'month', TRUE)
ON CONFLICT (id) DO NOTHING;

WITH sample_developers (developer_no, display_name) AS (
    VALUES
        (1, 'Avery Johnson'),
        (2, 'Jordan Lee'),
        (3, 'Morgan Patel'),
        (4, 'Taylor Chen'),
        (5, 'Casey Rodriguez'),
        (6, 'Riley Kim'),
        (7, 'Cameron Davis'),
        (8, 'Quinn Wilson'),
        (9, 'Parker Thompson'),
        (10, 'Reese Martin'),
        (11, 'Rowan Garcia'),
        (12, 'Skyler Anderson'),
        (13, 'Drew Thomas'),
        (14, 'Finley Moore'),
        (15, 'Alex Jackson'),
        (16, 'Emerson White'),
        (17, 'Sage Harris'),
        (18, 'Dakota Clark'),
        (19, 'Jamie Lewis'),
        (20, 'Blake Robinson'),
        (21, 'Elliot Walker'),
        (22, 'Kendall Young'),
        (23, 'Micah Allen'),
        (24, 'Logan King'),
        (25, 'Harper Wright'),
        (26, 'Arden Scott'),
        (27, 'Noah Green'),
        (28, 'Mila Baker'),
        (29, 'Ethan Adams'),
        (30, 'Zoe Nelson'),
        (31, 'Luca Hill'),
        (32, 'Ivy Campbell'),
        (33, 'Owen Mitchell'),
        (34, 'Nina Perez'),
        (35, 'Theo Roberts'),
        (36, 'Maya Turner'),
        (37, 'Leo Phillips'),
        (38, 'Aria Evans'),
        (39, 'Kai Edwards'),
        (40, 'Lena Collins'),
        (41, 'Ezra Stewart'),
        (42, 'Isla Sanchez'),
        (43, 'Milo Morris'),
        (44, 'Ada Rogers'),
        (45, 'Jude Reed'),
        (46, 'Eden Cook'),
        (47, 'Nico Morgan'),
        (48, 'Remy Bell'),
        (49, 'Sofia Murphy'),
        (50, 'Amir Bailey')
),
prepared_developers AS (
    SELECT
        developer_no,
        display_name,
        LOWER(REGEXP_REPLACE(display_name, '[^A-Za-z0-9]+', '.', 'g'))
            || '.' || LPAD(developer_no::TEXT, 2, '0')
            || '@example.test' AS email
    FROM sample_developers
)
INSERT INTO users (id, email, password_hash, display_name)
SELECT
    ('10000000-0000-4000-8000-' || LPAD(developer_no::TEXT, 12, '0'))::UUID,
    email,
    crypt(ENCODE(gen_random_bytes(32), 'hex'), gen_salt('bf', 12)),
    display_name
FROM prepared_developers
ON CONFLICT (id) DO NOTHING;

INSERT INTO subscriptions (
    id,
    user_id,
    plan_id,
    status,
    starts_at,
    current_period_start,
    current_period_end
)
SELECT
    ('20000000-0000-4000-8000-' || LPAD(n::TEXT, 12, '0'))::UUID,
    ('10000000-0000-4000-8000-' || LPAD(n::TEXT, 12, '0'))::UUID,
    plans.id,
    'active',
    date_trunc('month', CURRENT_TIMESTAMP),
    date_trunc('month', CURRENT_TIMESTAMP),
    date_trunc('month', CURRENT_TIMESTAMP) + INTERVAL '1 month'
FROM GENERATE_SERIES(1, 50) AS series(n)
JOIN subscription_plans AS plans
    ON plans.code = CASE
        WHEN n <= 20 THEN 'free'
        WHEN n <= 40 THEN 'pro'
        ELSE 'enterprise'
    END
ON CONFLICT (id) DO NOTHING;

INSERT INTO usage_quotas (
    id,
    subscription_id,
    metric,
    period,
    quota_limit,
    is_hard_limit
)
SELECT
    ('40000000-0000-4000-8000-' || LPAD(n::TEXT, 12, '0'))::UUID,
    ('20000000-0000-4000-8000-' || LPAD(n::TEXT, 12, '0'))::UUID,
    'requests',
    'day',
    CASE
        WHEN n <= 20 THEN 1000
        WHEN n <= 40 THEN 100000
        ELSE 1000000
    END,
    FALSE
FROM GENERATE_SERIES(1, 50) AS series(n)
ON CONFLICT (id) DO NOTHING;

-- These generated credentials are intentionally unusable, revoked fixtures.
-- Only HMAC hashes are inserted; transient key and HMAC bytes are not retained.
WITH key_material AS (
    SELECT
        n,
        ('10000000-0000-4000-8000-' || LPAD(n::TEXT, 12, '0'))::UUID AS user_id,
        gen_random_bytes(32) AS transient_key,
        gen_random_bytes(32) AS transient_hmac_secret,
        CURRENT_TIMESTAMP AS created_at
    FROM GENERATE_SERIES(1, 50) AS series(n)
)
INSERT INTO api_keys (
    id,
    user_id,
    name,
    key_prefix,
    key_hash,
    created_at,
    revoked_at
)
SELECT
    ('30000000-0000-4000-8000-' || LPAD(n::TEXT, 12, '0'))::UUID,
    user_id,
    'Seed fixture key ' || LPAD(n::TEXT, 3, '0'),
    'seed_' || LPAD(n::TEXT, 3, '0'),
    ENCODE(HMAC(transient_key, transient_hmac_secret, 'sha256'), 'hex'),
    created_at,
    created_at
FROM key_material
ON CONFLICT (id) DO NOTHING;

COMMIT;
