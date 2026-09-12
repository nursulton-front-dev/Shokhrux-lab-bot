"""Bound memory, nesting, fields and numbers before merchant business parsing."""
import asyncio
import json
from decimal import Decimal

MAX_FIELDS = 32
MAX_DEPTH = 5
MAX_NODES = 128


async def read_body(request, limit: int) -> bytes:
    if request.headers.get('Content-Encoding', 'identity').lower() != 'identity':
        raise ValueError('Compressed callback bodies are not accepted')
    if request.content_length is not None and request.content_length > limit:
        raise ValueError('Body too large')
    body = bytearray()
    async with asyncio.timeout(5):
        while True:
            chunk = await request.content.read(min(4096, limit + 1 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > limit:
                raise ValueError('Body too large')
    return bytes(body)


def _number(value):
    if len(value) > 19:
        raise ValueError('Number too long')
    number = int(value)
    if not -(2**63) <= number <= 2**63-1:
        raise ValueError('Number out of range')
    return number


def _decimal(value):
    if len(value) > 32 or 'e' in value.lower():
        raise ValueError('Decimal out of range')
    return Decimal(value)


def _pairs(pairs):
    if len(pairs) > MAX_FIELDS:
        raise ValueError('Too many fields')
    result = {}
    for key, value in pairs:
        if len(key) > 64 or key in result:
            raise ValueError('Invalid or duplicate field')
        result[key] = value
    return result


def load_json(body: bytes):
    # Scan depth before json.loads: recursive payloads never reach the decoder.
    depth = 0
    quoted = escaped = False
    for char in body:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (91, 123):
            depth += 1
            if depth > MAX_DEPTH:
                raise ValueError('JSON too deep')
        elif char in (93, 125):
            depth -= 1
    def reject_constant(value):
        raise ValueError('Non-finite number')
    payload = json.loads(body, parse_int=_number, parse_float=_decimal,
                         parse_constant=reject_constant, object_pairs_hook=_pairs)
    stack = [payload]
    nodes = 0
    while stack:
        value = stack.pop()
        nodes += 1
        if nodes > MAX_NODES:
            raise ValueError('Too many JSON values')
        if isinstance(value, dict):
            stack.extend(value.keys())
            stack.extend(value.values())
        elif isinstance(value, list):
            raise ValueError('Arrays are not accepted in merchant requests')
        elif isinstance(value, str):
            if len(value) > 512:
                raise ValueError('String too long')
            value.encode('utf-8')  # reject lone surrogates before echo/logging
    return payload
