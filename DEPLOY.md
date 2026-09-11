# Deployment Guide — Shokhrux Lab Fitness Bot

## 0. Prerequisites
- A Telegram bot token, admin IDs, and the main closed channel ID (`CHANNEL_ID`).
  The bot must be **admin** there (create/revoke invite links, ban members).
- A closed **VIP group** (`VIP_CHAT_ID`) for 6-month clients. The bot must be
  admin there with **Ban users** and **Invite users via link** rights — it
  auto-issues personal invites on VIP purchase and auto-kicks on expiry.
- A PostgreSQL database (Neon cloud recommended) and a Google Gemini API key.
- `DATABASE_URL` must NOT contain `channel_binding=require` — asyncpg does not support it and
  `bot/database/db.py` refuses to start rather than silently downgrading the connection.
- Tariff banners are per language: `assets/Tarifs_uz.jpg` and `assets/Tarifs_ru.jpg`
  (override with `TARIFFS_IMG_UZ` / `TARIFFS_IMG_RU`).
- Copy `.env.example` → `.env` and fill in every value.
- Existing DB? Run `python run_migration.py` before starting this version. It adds payment idempotency keys, the durable delivery table, and query indexes. Errors stop deployment.

## 1. Self-test (run before every deploy)
```bash
python self_test.py
```
Exits 0 when all handlers, routers, texts, keyboards and helpers are healthy.

## 2. Option A — Docker (recommended)
```bash
cp .env.example .env      # then edit .env
docker compose build
docker compose stop bot
docker compose run --rm bot python run_migration.py
# Existing installation with old invite links: rotate them before starting the new bot.
docker compose run --rm bot python rotate_invites.py
docker compose up -d
docker compose logs -f bot
```
- Uses Neon by default via `DATABASE_URL`.
- The app runs as UID/GID 10001, with `TZ=Asia/Tashkent` and a 60-second stop grace period.
- Logs use the named `bot_logs` volume; assets use `bot_assets`, initialized from the image on first creation. Existing host `./logs` is retained but no longer written; existing banners are baked from `./assets` at build time. **The named volume shadows the image layer: rebuilding does NOT refresh banners.** After changing `assets/`, copy them in explicitly:
  ```bash
  docker cp assets/Tarifs_ru.jpg fitness_bot:/app/assets/Tarifs_ru.jpg
  docker cp assets/Tarifs_uz.jpg fitness_bot:/app/assets/Tarifs_uz.jpg
  ```
  Do not delete volumes to update the app.
- Docker stdout rotates at 10 MB × 3; the app file rotates at 5 MB plus five backups.
- To run a local Postgres instead of Neon:
  ```bash
  docker compose --profile local-db up -d
  # set DATABASE_URL=postgresql+asyncpg://fitness:fitness@postgres:5432/fitness_bot
  ```

## 3. Option B — systemd on Ubuntu VPS
```bash
sudo useradd -r -m -d /opt/fitness_bot fitnessbot        # service user
sudo cp -r . /opt/fitness_bot && cd /opt/fitness_bot
sudo -u fitnessbot python3 -m venv .venv
sudo -u fitnessbot .venv/bin/pip install -r requirements.txt
sudo -u fitnessbot cp .env.example .env                  # then edit .env
sudo mkdir -p /opt/fitness_bot/logs && sudo chown fitnessbot:fitnessbot /opt/fitness_bot/logs

sudo cp fitness_bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fitness_bot
sudo systemctl status fitness_bot
journalctl -u fitness_bot -f
```

## 4. Database migrations
On first run the bot auto-creates tables (`init_db`). For an existing DB missing
newer columns, run once:
```bash
python run_migration.py
```
`reset_db.py` / `clear_db.py` **drop data** — use only in development.

## 5. Logging
- App writes `bot.log` (rotating) in the working dir; override path with `LOG_FILE`.
- Under Docker the path is `/app/logs/bot.log`; under systemd stdout also goes to journald.

## 6. Audit fixes: rollout and operating contract
- Run one polling process per bot token. FSM isolation, the outbound Telegram limiter and in-memory broadcasts are per process. Payment serialization/idempotency and delivery jobs live in PostgreSQL.
- Both channels require `can_invite_users` and membership-management rights. New links use join requests: only the paid Telegram user whose stored URL matches is approved. Unknown/forwarded URLs are declined.
- `rotate_invites.py` contacts Telegram, revokes historical stored links (including expired subscriptions), and sends replacements to active subscribers. Run it once during upgrade; retry if it exits nonzero. Untracked links created by the old manual admin handler cannot be found through Bot API listing: revoke those in Telegram's invite management UI.
- Money is committed together with a durable delivery job. The worker checks every 60 seconds; Telegram errors retry with backoff up to one hour. Inspect `Payment delivery failed` logs and `payment_deliveries` where `completed_at IS NULL` and `attempts > 0`.
- Message delivery is at least once: a network timeout after Telegram accepts a message may produce a duplicate notification. Payment status, balance, subscription and referral accrual are protected independently.
- Cashback is checked again at confirmation. It is not reserved while a manual payment is pending. If another purchase used that cashback, confirmation fails without extending access: an administrator must reconcile the received cash and cashback terms before retrying or refunding.
- Rahmat Pay is disabled: the previous URL builder was a stub. Enabling online payments requires the provider's documented invoice API and authenticated confirmation/reconciliation. Manual card approval and full cashback payments remain available.
- Default DB connection budget is 5 per process (`DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=0`), recycle 600 s, pool wait 10 s, connect timeout 15 s, command timeout 30 s. Budget all processes and maintenance connections against the actual Neon compute/pooler quota; these values do not prove an account-specific capacity limit.
- `pool_pre_ping` replaces stale idle connections but cannot replay a transaction interrupted by a disconnect. Repeat the same payment action after checking its persisted status; do not blindly retry every handler's external effects.
- Supported verification environment: Python 3.13 with a temporary local PostgreSQL 17.9, and offline Telegram/Gemini doubles. Docker image targets Python 3.12 and still needs a deployment smoke test on the actual host.

## 7. Payme Merchant API

The bot serves Payme's JSON-RPC callbacks at `POST /api/payme` from the same
process as Telegram polling (`payme-endpoint` worker), bound to
`PAYME_HOST:PAYME_PORT` (default `0.0.0.0:8000`, published on the host as
`127.0.0.1:8000`). nginx proxies the public route to it.

- Credentials: `PAYME_MERCHANT_ID`, `PAYME_TEST_KEY`, `PAYME_PROD_KEY`.
  `PAYME_SANDBOX` selects which key authenticates callbacks — exactly one key is
  accepted at a time, so a test key can never sign production calls.
- Launch gate: `PAYME_CHECKOUT_PAUSED` (default `True`). While on, the Merchant
  API endpoint keeps answering Payme's callbacks, but payers see the Payme button
  marked "(Tez kunda)" and a tap shows a "coming soon" alert instead of minting
  an order. Set it to `False` and restart the bot to open Payme checkout.
- Auth is HTTP Basic: login `Paycom` (the merchant id is also accepted),
  password = the active key. Every failure is returned as HTTP 200 with a
  JSON-RPC error, as Payme expects.
- Account parameter: `order_id`, which is `payments.id`. Amounts are quoted in
  tiyin (1 UZS = 100 tiyin).
- Implemented methods: `CheckPerformTransaction`, `CreateTransaction`,
  `PerformTransaction`, `CancelTransaction`, `CheckTransaction`, `GetStatement`.
- `payme_transactions` owns the protocol state machine. A partial unique index
  on `payment_id WHERE state IN (1, 2)` makes double payment of one order
  impossible; `payme_id` is the idempotency key for retries.
- Performing a real order calls `process_successful_payment`, so the
  subscription, cashback ledger and delivery job commit in one transaction.
  A performed real order cannot be cancelled through the API (`-31007`):
  channel access is already granted, so refunds are a support decision.
- Unconfirmed transactions older than 12 hours are cancelled with reason 4.

### Sandbox orders
`create_payme_sandbox_orders.py` seeds order 101 (150 000 UZS) and 102
(300 000 UZS) as `payment_method = payme_sandbox`, owned by a synthetic user
(`telegram_id = -1`). They carry `tariff_months = 0`, which matches no entry in
`TARIFF_PRICES`, so they cannot grant a subscription even by mistake; performing
one only marks it paid. Sandbox orders are invisible when `PAYME_SANDBOX=False`.

```bash
docker exec -w /app fitness_bot python create_payme_sandbox_orders.py
```

## 8. Regression checks
```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q tests
python self_test.py
python audit/benchmark_event_loop.py
```
Tests ignore `.env`; PostgreSQL tests create and delete only their own temporary local cluster via `pgembed`. Neither production Neon nor real Telegram/Gemini are contacted by tests. `self_test.py` is the original import/wiring smoke suite and does not prove financial concurrency on its own.
