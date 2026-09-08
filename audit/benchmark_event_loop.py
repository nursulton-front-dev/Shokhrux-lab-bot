"""Compare identical rendering on the event loop and on a worker thread.

No .env, Telegram, Gemini or database access. This is a synthetic latency probe,
not a measurement of production p95 or Neon network behavior.
"""
import asyncio
import datetime as dt
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch("pydantic_settings.DotEnvSettingsSource.__call__", return_value={}):
    from bot.handlers.admin import ExportUser, ExportSubscription, ExportPayment, _render_styled_excel
    from bot.services.charts import generate_weight_chart


async def measure(render, in_thread: bool) -> dict[str, float]:
    gaps = []
    stopped = False
    async def pulse():
        while not stopped:
            start = time.perf_counter()
            await asyncio.sleep(0.005)
            gaps.append(time.perf_counter() - start)
    ticker = asyncio.create_task(pulse())
    await asyncio.sleep(0.02)
    start = time.perf_counter()
    result = await asyncio.to_thread(render) if in_thread else render()
    elapsed = time.perf_counter() - start
    (result[0] if isinstance(result, tuple) else result).close()
    await asyncio.sleep(0.02)
    stopped = True
    await ticker
    return {"render_seconds": round(elapsed, 4), "max_heartbeat_gap_seconds": round(max(gaps), 4)}


async def main() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    users = [ExportUser(i, f"user{i}", f"Test user {i}", "+998901234567", "ru", 0, None, now) for i in range(1, 1001)]
    subs = [ExportSubscription(i, "active", 6, now + dt.timedelta(days=180)) for i in range(1, 1001)]
    payments = [ExportPayment(i, i, "completed", 6, 2300000, 0, now) for i in range(1, 1001)]
    records = [(now + dt.timedelta(days=i), 90 - i/100) for i in range(1000)]
    jobs = {"xlsx_1000_users_1000_payments": lambda: _render_styled_excel(users, subs, payments, now.replace(tzinfo=None)),
            "chart_1000_points": lambda: generate_weight_chart(records)}
    output = {}
    for name, render in jobs.items():
        output[name] = {"synchronous": await measure(render, False), "to_thread": await measure(render, True)}
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
