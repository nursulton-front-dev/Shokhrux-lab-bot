"""Per-IP request throttle shared by the merchant callback endpoints.

Payme and Click both retry aggressively, so this only sheds an obvious flood.
Every endpoint authenticates each request regardless of the verdict here.
"""
import time
from collections import deque

from aiohttp import web

MAX_TRACKED_ADDRESSES = 1000
IDLE_EVICTION_SECONDS = 60.0

Buckets = dict[str, deque[float]]


def client_ip(request: web.Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote or "unknown"


def allow(buckets: Buckets, address: str, *, limit: int, window: float) -> bool:
    """Record the request and report whether it stays inside the window."""
    now = time.monotonic()
    bucket = buckets.setdefault(address, deque())
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    if len(buckets) > MAX_TRACKED_ADDRESSES:
        # Bound memory without a background sweeper.
        stale = [a for a, b in buckets.items() if not b or now - b[-1] > IDLE_EVICTION_SECONDS]
        for address_to_drop in stale:
            buckets.pop(address_to_drop, None)
    return True
