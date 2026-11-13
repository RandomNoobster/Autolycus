"""
Simple in-process sliding-window rate limits for quota-sensitive endpoints.

Keyed by Discord session user when present, otherwise by client IP.
Suitable for a single Waitress process (shared thread memory).
"""
from __future__ import annotations

import ipaddress
from collections import deque
from functools import wraps
from threading import Lock
from time import monotonic
from typing import Any, Callable, Deque, TypeVar

from flask import jsonify, request

F = TypeVar('F', bound=Callable[..., Any])

_lock = Lock()
_hits: dict[str, Deque[float]] = {}
# Idle buckets are dropped every _SWEEP_EVERY calls, so memory tracks active clients
# rather than every client ever seen.
_SWEEP_EVERY = 1000
_calls_since_sweep = 0
_longest_window = 0.0


def _client_address() -> str:
    """Client address for anonymous limits; IPv6 is grouped by /64.

    One IPv6 subscriber usually controls a whole /64, so keying single
    addresses would let them rotate through it to dodge the limit.
    """
    raw = request.remote_addr or "unknown"
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return raw
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def _client_key(scope: str) -> str:
    user_id = getattr(request, 'session_user_id', None)
    if user_id is not None:
        return f'{scope}:user:{user_id}'
    return f'{scope}:ip:{_client_address()}'


def _sweep_idle_buckets(now: float) -> None:
    """Delete buckets with no hit inside the longest window in use. Caller holds _lock."""
    cutoff = now - _longest_window
    for key in [k for k, bucket in _hits.items() if not bucket or bucket[-1] < cutoff]:
        del _hits[key]


def try_acquire_rate_limit(
    max_requests: int,
    window_seconds: int,
    *,
    scope: str,
) -> bool:
    """
    Record a hit if under the limit.

    Returns True when the caller may proceed with the protected work,
    False when the limit is already exhausted (no hit recorded).
    """
    global _calls_since_sweep, _longest_window
    key = _client_key(scope)
    now = monotonic()
    cutoff = now - window_seconds
    with _lock:
        _longest_window = max(_longest_window, float(window_seconds))
        _calls_since_sweep += 1
        if _calls_since_sweep >= _SWEEP_EVERY:
            _calls_since_sweep = 0
            _sweep_idle_buckets(now)
        bucket = _hits.setdefault(key, deque())
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= max_requests:
            return False
        bucket.append(now)
        return True


def rate_limit(max_requests: int, window_seconds: int, *, scope: str) -> Callable[[F], F]:
    """Allow at most `max_requests` calls per `window_seconds` for this scope."""

    def decorator(f: F) -> F:
        @wraps(f)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if not try_acquire_rate_limit(max_requests, window_seconds, scope=scope):
                key = _client_key(scope)
                now = monotonic()
                with _lock:
                    bucket = _hits.get(key)
                    oldest = bucket[0] if bucket else now
                retry_after = max(1, int(window_seconds - (now - oldest)) + 1)
                response = jsonify({
                    'error': 'Too many requests',
                    'message': (
                        f'Rate limit exceeded ({max_requests} per '
                        f'{window_seconds}s). Please slow down.'
                    ),
                    'code': 'RATE_LIMITED',
                })
                response.status_code = 429
                response.headers['Retry-After'] = str(retry_after)
                return response
            return f(*args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator
