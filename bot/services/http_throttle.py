"""Bounded per-IP throttle; forwarded headers require an explicit trusted peer."""
import ipaddress
import time
from collections import deque
from functools import lru_cache

from aiohttp import web
from bot.config import config

MAX_TRACKED_ADDRESSES = 1000
IDLE_EVICTION_SECONDS = 60.0
Buckets = dict[str, deque[float]]


@lru_cache(maxsize=8)
def trusted_networks(value: str):
    return tuple(ipaddress.ip_network(part.strip(), strict=False) for part in value.split(',') if part.strip())


def _ip(value):
    if not isinstance(value, str) or len(value) > 45:
        return None
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def client_ip(request: web.Request) -> str:
    peer = _ip(request.remote)
    if peer is None:
        return 'unknown'
    if any(peer in network for network in trusted_networks(config.trusted_proxy_ips)):
        # Nginx MUST overwrite X-Real-IP with its connection peer ($remote_addr).
        real = _ip(request.headers.get('X-Real-IP'))
        if real is not None:
            return str(real)
    return str(peer)


def allow(buckets: Buckets, address: str, *, limit: int, window: float) -> bool:
    now = time.monotonic()
    if address not in buckets and len(buckets) >= MAX_TRACKED_ADDRESSES:
        # Evict expired entries only. New identities cannot evict a throttled IP
        # to reset its quota, and the dictionary never exceeds the hard cap.
        for key in list(buckets):
            if not buckets[key] or now - buckets[key][-1] > max(window, IDLE_EVICTION_SECONDS):
                del buckets[key]
        if len(buckets) >= MAX_TRACKED_ADDRESSES:
            return False
    bucket = buckets.setdefault(address, deque())
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True
