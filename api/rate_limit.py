"""
Simple in-process sliding-window rate limits for quota-sensitive endpoints.

Keyed by Discord session user when present, otherwise by client IP.
Suitable for a single Waitress process (shared thread memory).
"""
from __future__ import annotations

from collections import defaultdict, deque
from functools import wraps
from threading import Lock
from time import monotonic
from typing import Any, Callable, Deque, TypeVar

from flask import jsonify, request

F = TypeVar('F', bound=Callable[..., Any])

_lock = Lock()
_hits: dict[str, Deque[float]] = defaultdict(deque)


def _client_key(scope: str) -> str:
    user_id = getattr(request, 'session_user_id', None)
    if user_id is not None:
        return f'{scope}:user:{user_id}'
    return f'{scope}:ip:{request.remote_addr or "unknown"}'


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
    key = _client_key(scope)
    now = monotonic()
    cutoff = now - window_seconds
    with _lock:
        bucket = _hits[key]
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
                    bucket = _hits[key]
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
