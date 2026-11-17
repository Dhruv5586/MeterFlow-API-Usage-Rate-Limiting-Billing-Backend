from sqlalchemy import text
from app.core.config import settings
from sqlalchemy import create_engine
from tests.conftest import test_engine

dev_engine = create_engine(settings.assemble_db_connection(settings.DATABASE_URL))

tables = ['users', 'subscription_plans', 'subscriptions', 'api_keys', 'usage_events', 'usage_daily', 'invoices', 'payments']

print('--- NEONDB (DEV) COUNTS ---')
with dev_engine.connect() as conn:
    for t in tables:
        cnt = conn.execute(text(f"SELECT count(*) FROM {t}")).scalar()
        print(f"{t}: {cnt}")

print('\n--- NEONDB_TEST (TEST) COUNTS ---')
with test_engine.connect() as conn:
    for t in tables:
        cnt = conn.execute(text(f"SELECT count(*) FROM {t}")).scalar()
        print(f"{t}: {cnt}")
