import json
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from unittest.mock import AsyncMock

from bot.config import config
from bot.services import http_throttle as throttle
from bot.services.http_payload import load_json
from bot.services.click import api


def test_untrusted_peer_cannot_spoof_ip(monkeypatch):
    monkeypatch.setattr(config, 'trusted_proxy_ips', '127.0.0.1')
    request = SimpleNamespace(remote='203.0.113.8', headers={'X-Real-IP': '8.8.8.8', 'X-Forwarded-For': '1.1.1.1'})
    assert throttle.client_ip(request) == '203.0.113.8'


def test_trusted_proxy_uses_only_valid_single_real_ip(monkeypatch):
    monkeypatch.setattr(config, 'trusted_proxy_ips', '127.0.0.1,::1')
    request = SimpleNamespace(remote='127.0.0.1', headers={'X-Real-IP': '203.0.113.8', 'X-Forwarded-For': 'spoof'})
    assert throttle.client_ip(request) == '203.0.113.8'
    for invalid in ['1.2.3.4, 5.6.7.8', 'x'*10000, 'garbage']:
        request.headers['X-Real-IP'] = invalid
        assert throttle.client_ip(request) == '127.0.0.1'


def test_throttle_cap_cannot_be_used_to_reset_existing_quota(monkeypatch):
    monkeypatch.setattr(throttle, 'MAX_TRACKED_ADDRESSES', 3)
    buckets = {}
    for key in ('a', 'b', 'c'):
        assert throttle.allow(buckets, key, limit=1, window=10)
    for i in range(100):
        assert not throttle.allow(buckets, str(i), limit=1, window=10)
    assert len(buckets) == 3
    assert not throttle.allow(buckets, 'a', limit=1, window=10)


@pytest.mark.parametrize('body', [
    b'{"a":1,"a":2}', b'['*1000+b']'*1000,
    json.dumps({str(i): i for i in range(33)}).encode(),
    b'{"a":NaN}', b'{"a":1e999999}', b'{"a":999999999999999999999}',
    b'{"a":"'+b'x'*513+b'"}', b'{"a":"\\ud800"}',
])
def test_bounded_json_refuses_hostile_structures(body):
    with pytest.raises(ValueError):
        load_json(body)


@pytest.mark.asyncio
@pytest.mark.parametrize('body,content_type', [
    (b'a=1&a=2', 'application/x-www-form-urlencoded'),
    (b'&'.join(b'a=1' for _ in range(100)), 'application/x-www-form-urlencoded'),
    (b'{"amount":{"nested":1}}', 'application/json'),
    (b'['*1000+b']'*1000, 'application/json'),
    (b'x'*(16*1024+1), 'application/x-www-form-urlencoded'),
])
async def test_click_invalid_bodies_return_protocol_error_without_db(body, content_type, monkeypatch):
    factory = AsyncMock()
    monkeypatch.setattr(api, 'AsyncSessionLocal', factory)
    app = web.Application(handler_args={'auto_decompress': False})
    api.register_routes(app, AsyncMock())
    async with TestClient(TestServer(app)) as client:
        response = await client.post(api.CLICK_PREPARE_PATH, data=body, headers={'Content-Type': content_type})
        assert response.status == 200
        assert (await response.json())['error'] == -8
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_chunked_body_is_bounded_without_content_length(monkeypatch):
    factory = AsyncMock()
    monkeypatch.setattr(api, 'AsyncSessionLocal', factory)
    app = web.Application(handler_args={'auto_decompress': False})
    api.register_routes(app, AsyncMock())
    async def chunks():
        for _ in range(20):
            yield b'x'*1024
    async with TestClient(TestServer(app)) as client:
        response = await client.post(api.CLICK_PREPARE_PATH, data=chunks())
        assert response.status == 200
        assert (await response.json())['error'] == -8
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_compressed_callback_is_rejected_without_inflating():
    import gzip
    from bot.services.payment_server import create_app
    app = create_app(AsyncMock())
    async with TestClient(TestServer(app)) as client:
        response = await client.post(api.CLICK_PREPARE_PATH, data=gzip.compress(b'x'*1000000),
                                     headers={'Content-Encoding': 'gzip'})
        assert response.status == 200
        assert (await response.json())['error'] == -8
