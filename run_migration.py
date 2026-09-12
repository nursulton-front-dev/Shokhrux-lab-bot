"""Idempotent additive migration. Failures must fail deployment visibly."""
import asyncio

from sqlalchemy import text

from bot.database.db import engine, init_db
from bot.database.audit_migration import migrate_audit_fields


async def main() -> None:
    try:
        await init_db()
        columns = (
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS language VARCHAR(5)",
            "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS invite_link VARCHAR",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS balance INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT",
            "ALTER TABLE payments ADD COLUMN IF NOT EXISTS cashback_applied INTEGER DEFAULT 0",
            "ALTER TABLE user_fitness_profiles ADD COLUMN IF NOT EXISTS initial_weight_kg DOUBLE PRECISION",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_file_id VARCHAR",
            "ALTER TABLE user_fitness_profiles ADD COLUMN IF NOT EXISTS gender VARCHAR DEFAULT 'M'",
            "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS vip_invite_link VARCHAR",
            "ALTER TABLE payments ADD COLUMN IF NOT EXISTS request_key VARCHAR(160)",
        )
        async with engine.begin() as conn:
            # Bound the wait for live traffic, instead of blocking deployment forever.
            await conn.execute(text("SET LOCAL lock_timeout = '10s'"))
            for statement in columns:
                await conn.execute(text(statement))
        async with engine.begin() as conn:
            await migrate_audit_fields(conn)
        async with engine.connect() as conn:
            conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
            for statement in (
                "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ix_click_transactions_active_order ON click_transactions(payment_id) WHERE state IN (1, 2)",
                "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ix_payments_request_key ON payments(request_key)",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_subscriptions_user_status_expiry ON subscriptions(user_id, status, expires_at)",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_subscriptions_status_expiry ON subscriptions(status, expires_at)",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_payments_user_status ON payments(user_id, status)",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_payments_status_created ON payments(status, created_at)",
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_payme_transactions_payme_time ON payme_transactions(payme_time)",
                "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ix_payme_transactions_active_order ON payme_transactions(payment_id) WHERE state IN (1, 2)",
            ):
                # A killed CREATE INDEX CONCURRENTLY leaves an INVALID index;
                # IF NOT EXISTS alone would silently skip it on every retry.
                index_name = statement.split("EXISTS ", 1)[1].split(" ", 1)[0]
                valid = await conn.scalar(text(
                    "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE c.relname=:name AND n.nspname=current_schema()"
                ), {"name": index_name})
                if valid is False:
                    # index_name only comes from the fixed statements above.
                    await conn.execute(text(f'DROP INDEX CONCURRENTLY "{index_name}"'))
                await conn.execute(text(statement))
        print("Database migration completed successfully.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
