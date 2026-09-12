"""Run during a stopped-writer deployment; all holds are backfilled atomically."""
from sqlalchemy import text


async def migrate_audit_fields(conn) -> None:
    await conn.execute(text("SET LOCAL lock_timeout = '10s'"))
    await conn.execute(text('LOCK TABLE users, payments, payment_deliveries IN SHARE ROW EXCLUSIVE MODE'))
    for statement in (
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS reserved_cashback INTEGER NOT NULL DEFAULT 0',
        'ALTER TABLE payments ADD COLUMN IF NOT EXISTS cashback_reserved INTEGER NOT NULL DEFAULT 0',
        'ALTER TABLE payment_deliveries ADD COLUMN IF NOT EXISTS lease_token VARCHAR(32)',
        'ALTER TABLE payment_deliveries ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ',
        'ALTER TABLE payment_deliveries ADD COLUMN IF NOT EXISTS last_error VARCHAR(500)',
    ):
        await conn.execute(text(statement))
    # Do not silently reprice/cancel legacy orders for which the provider may have
    # already accepted payment. Fail deployment and leave the transaction unchanged.
    conflict = await conn.scalar(text('''
        SELECT u.telegram_id FROM users u LEFT JOIN (
            SELECT user_id, SUM(cashback_applied) AS held FROM payments
            WHERE status='pending' GROUP BY user_id
        ) p ON p.user_id=u.telegram_id
        WHERE COALESCE(p.held,0) > COALESCE(u.balance,0)
        OR u.balance < 0 LIMIT 1
    '''))
    if conflict is not None:
        raise RuntimeError(f'Cashback reconciliation required before deployment: user_id={conflict}')
    await conn.execute(text("UPDATE payments SET cashback_reserved = CASE WHEN status='pending' THEN COALESCE(cashback_applied,0) ELSE 0 END"))
    await conn.execute(text('''
        UPDATE users u SET reserved_cashback = (
            SELECT COALESCE(SUM(p.cashback_reserved),0) FROM payments p WHERE p.user_id=u.telegram_id
        )
    '''))
    for table, name, predicate in (
        ('users', 'ck_users_cashback_hold', 'reserved_cashback >= 0 AND reserved_cashback <= balance'),
        ('payments', 'ck_payments_cashback_hold', 'cashback_reserved >= 0'),
    ):
        # All identifiers/predicates come from this fixed allowlist.
        await conn.execute(text(f"""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='{name}' AND conrelid='{table}'::regclass) THEN
                    ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({predicate});
                END IF;
            END $$
        """))
