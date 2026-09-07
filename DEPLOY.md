# Deployment Guide — Shokhrux Lab Fitness Bot

## 0. Prerequisites
- A Telegram bot token, admin IDs, and the main closed channel ID (`CHANNEL_ID`).
  The bot must be **admin** there (create/revoke invite links, ban members).
- A closed **VIP group** (`VIP_CHAT_ID`) for 6-month clients. The bot must be
  admin there with **Ban users** and **Invite users via link** rights — it
  auto-issues personal invites on VIP purchase and auto-kicks on expiry.
- A PostgreSQL database (Neon cloud recommended) and a Google Gemini API key.
- Copy `.env.example` → `.env` and fill in every value.
- Existing DB? Run `python run_migration.py` to add the `vip_invite_link` column.

## 1. Self-test (run before every deploy)
```bash
python self_test.py
```
Exits 0 when all handlers, routers, texts, keyboards and helpers are healthy.

## 2. Option A — Docker (recommended)
```bash
cp .env.example .env      # then edit .env
docker compose build
docker compose up -d
docker compose logs -f bot
```
- Uses Neon by default via `DATABASE_URL`.
- Logs persist in `./logs/bot.log` (rotating, 5 MB × 5), assets in `./assets`.
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
