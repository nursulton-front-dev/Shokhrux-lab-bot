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
- Money is committed together with a durable delivery job. The worker checks every 3 seconds; Telegram errors retry with backoff up to one hour. Inspect `Payment delivery failed` logs and `payment_deliveries` where `completed_at IS NULL` and `attempts > 0`.
- Message delivery is at least once: a network timeout after Telegram accepts a message may produce a duplicate notification. Payment status, balance, subscription and referral accrual are protected independently.
- Cashback is reserved under a user row lock when an order is created. Confirmation consumes its hold; cancellation or expiry releases it. Other pending orders can use only the available balance.
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

## Audit fixes and Click video (2026-09-12)

Before starting this version, stop **all writers** (polling, payment HTTP endpoint,
scheduler and delivery workers) and run `python run_migration.py`. In Docker:

```sh
docker compose build bot
docker compose stop bot
docker compose run --rm bot python run_migration.py
docker compose up -d bot
```

Build the new image **before** running its migration (`docker compose build bot`);
the migration must come from the same version as the application. Never run an old
image after the migration: it does not respect cashback holds. For rollback, stop
writers and reconcile pending orders before choosing a compatible version.

The migration adds `users.reserved_cashback`, `payments.cashback_reserved` and
outbox lease fields (`lease_token`, `locked_until`, `last_error`). It backfills
pending-order holds atomically and is repeatable. If old pending orders promise
more cashback than their owner's balance, it stops with the affected user ID.
Reconcile those orders with the gateway before retrying; it never silently changes
an already-issued invoice's amount or cancels a possibly paid order.

Place the instructional video at `assets/click_instruction.mp4`, or configure
`CLICK_TUTORIAL_VIDEO_PATH`. Relative paths resolve from the project root. The
video must be nonempty and smaller than 50 MiB. Alternatively set
`CLICK_TUTORIAL_VIDEO_ID` to a video file_id issued to **this bot**; it takes priority.
The missing/invalid asset fallback retains the text instructions and payment URL.

Docker mounts `/app/assets` as a named volume. Rebuilding does not overwrite an
existing volume; copy the video into it after the container is created:

```sh
docker compose cp assets/click_instruction.mp4 bot:/app/assets/click_instruction.mp4
```

Checkout sends one video on entry. Its Back/Reopen buttons carry the original
payment ID so navigation does not create another invoice or cashback hold.

Replace the public Nginx payment locations with `deploy/nginx/merchant-proxy.conf`
(included inside the existing TLS `server` block), validate with `nginx -t`, then
reload. The fragment overwrites both IP headers and retains protocol errors for
oversized requests/upstream failures. Do not enable `real_ip_header` based on
untrusted internet input on this public server.

Set `TRUSTED_PROXY_IPS` to the **actual direct proxy peer** seen by aiohttp. Host
networking commonly uses `127.0.0.1,::1`; Docker port publishing commonly uses the
host bridge gateway, whose exact address must be checked for this deployment.
Leave it empty to ignore all forwarding headers. Do not use `0.0.0.0/0`, `::/0`
or trust all private networks. The API port must not be publicly accessible.

`PAYMENT_DELIVERY_CONCURRENCY=4` and `PAYMENT_DELIVERY_BATCH_SIZE=50` control batch
sending. Tasks have a 90-second lease, a 45-second operation timeout, and retries
from 5 seconds up to one hour. A crashed worker's lease expires automatically;
`last_error` and `attempts` identify delivery failures. Sending is at least once:
a Telegram timeout after successful delivery can still cause a duplicate message,
but the payment and subscription are committed once.

### Final banners and authorized prelaunch cleanup

The release includes `assets/Tarifs_uz.jpg`, `assets/Tarifs_ru.jpg` and
`assets/click_instruction.mp4`. Both complete tariff captions fit Telegram's
1024-character limit. Copy **all three** files into the existing asset volume;
rebuilding alone retains old banners:

```sh
docker compose cp assets/Tarifs_uz.jpg bot:/app/assets/Tarifs_uz.jpg
docker compose cp assets/Tarifs_ru.jpg bot:/app/assets/Tarifs_ru.jpg
docker compose cp assets/click_instruction.mp4 bot:/app/assets/click_instruction.mp4
```

A production wipe requires explicit operator authorization. Stop all writers,
save and validate a full PostgreSQL custom-format backup, then truncate all
application tables in one transaction. Preserve sequences (`CONTINUE IDENTITY`)
so old payment URLs cannot resolve to newly created orders. Include gateway
transactions, delivery jobs, support tickets and fitness history alongside users,
subscriptions, payments and cashback. Verify zero rows before starting workers.
Run the release migration after cleanup and before restarting the bot.
Database cleanup does not delete historical Telegram messages/keyboards.
