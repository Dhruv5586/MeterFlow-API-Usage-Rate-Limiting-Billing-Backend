# MeterFlow Entity-Relationship Diagram

The diagram shows the ten relational tables planned for PostgreSQL. All IDs
are UUIDs unless they are a date, counter, or business value. Crow's-foot
notation: `||` means exactly one, `o|` zero or one, and `o{` zero or many.

```mermaid
erDiagram
    USERS {
        uuid id PK
        text email UK
        text password_hash
        text display_name
        text status
        timestamptz created_at
        timestamptz updated_at
    }
    API_KEYS {
        uuid id PK
        uuid user_id FK
        text name
        text key_prefix
        char key_hash UK
        timestamptz created_at
        timestamptz expires_at
        timestamptz revoked_at
        timestamptz last_used_at
    }
    SUBSCRIPTION_PLANS {
        uuid id PK
        text code UK
        text name
        numeric price
        char currency
        text billing_interval
        boolean is_active
        timestamptz created_at
    }
    SUBSCRIPTIONS {
        uuid id PK
        uuid user_id FK
        uuid plan_id FK
        text status
        timestamptz starts_at
        timestamptz current_period_start
        timestamptz current_period_end
        timestamptz canceled_at
        boolean cancel_at_period_end
        timestamptz created_at
    }
    USAGE_EVENTS {
        uuid id PK
        uuid user_id FK
        uuid api_key_id FK
        uuid subscription_id FK
        text http_method
        text endpoint
        smallint status_code
        integer latency_ms
        bigint response_size_bytes
        text source_server_id
        text source_record_key UK
        timestamptz created_at
    }
    USAGE_DAILY {
        uuid id PK
        uuid user_id FK
        uuid subscription_id FK
        uuid api_key_id FK
        date usage_date
        text endpoint
        text http_method
        bigint request_count
        bigint successful_request_count
        bigint error_request_count
        bigint response_bytes
        bigint latency_sum_ms
        timestamptz updated_at
    }
    USAGE_QUOTAS {
        uuid id PK
        uuid subscription_id FK
        text metric
        text period
        bigint quota_limit
        boolean is_hard_limit
        timestamptz created_at
        timestamptz updated_at
    }
    INVOICES {
        uuid id PK
        uuid user_id FK
        uuid subscription_id FK
        text invoice_number UK
        text status
        char currency
        numeric subtotal
        numeric tax
        numeric total
        timestamptz issued_at
        timestamptz due_at
        timestamptz paid_at
        timestamptz created_at
    }
    INVOICE_ITEMS {
        uuid id PK
        uuid invoice_id FK
        text description
        numeric quantity
        numeric unit_price
        numeric line_amount
        timestamptz created_at
    }
    AUDIT_LOGS {
        uuid id PK
        uuid actor_user_id FK
        text action
        text entity_type
        uuid entity_id
        jsonb details
        timestamptz occurred_at
    }

    USERS ||--o{ API_KEYS : owns
    USERS ||--o{ SUBSCRIPTIONS : has_history
    SUBSCRIPTION_PLANS ||--o{ SUBSCRIPTIONS : selected_by
    USERS ||--o{ USAGE_EVENTS : makes
    API_KEYS ||--o{ USAGE_EVENTS : authenticates
    SUBSCRIPTIONS ||--o{ USAGE_EVENTS : accounts_for
    USERS ||--o{ USAGE_DAILY : scopes
    SUBSCRIPTIONS ||--o{ USAGE_DAILY : summarized_as
    API_KEYS ||--o{ USAGE_DAILY : summarized_for
    SUBSCRIPTIONS ||--o{ USAGE_QUOTAS : grants
    USERS ||--o{ INVOICES : billed
    SUBSCRIPTIONS ||--o{ INVOICES : billed_for
    INVOICES ||--|{ INVOICE_ITEMS : contains
    USERS o|--o{ AUDIT_LOGS : performs
```

`source_record_key` is a nullable idempotency key for an imported source row;
it contains a stable row identity, not a raw IP, API key, or user credential.
`USAGE_DAILY` is derived aggregation data, not a replacement for the event
ledger.
