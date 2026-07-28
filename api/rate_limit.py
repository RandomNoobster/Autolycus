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


def rate_limit(max_requests: int, window_seconds: int, *, scope: str) -> Callable[[F], F]:
    """Allow at most `max_requests` calls per `window_seconds` for this scope."""

    def decorator(f: F) -> F:
        @wraps(f)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            key = _client_key(scope)
            now = monotonic()
            cutoff = now - window_seconds
            with _lock:
                bucket = _hits[key]
                while bucket and bucket[0] < cutoff:
                    bucket.popleft()
                if len(bucket) >= max_requests:
                    retry_after = max(1, int(window_seconds - (now - bucket[0])) + 1)
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
                bucket.append(now)
            return f(*args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator
