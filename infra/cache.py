"""
Shared caching infrastructure for backend services and domain modules.

Uses aiocache for async-compatible memoization with TTL support.
Cache strategy: cache expensive logic/computation functions, not HTTP routes.
Cache keys ignore callable and module arguments (see build_key_ignoring_callables).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import types
from collections.abc import Mapping
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, TypeVar
from urllib.parse import unquote, urlparse

from aiocache import Cache, cached
from aiocache.serializers import PickleSerializer

logger = logging.getLogger(__name__)

# --- Configuration ---

# TTL values in seconds
TTL_PRICES = 300          # 5 minutes - trade prices update ~hourly
TTL_GAME_DATA = 600       # 10 minutes - colors, radiation, treasures
TTL_REVENUE_CONTEXT = 300 # 5 minutes - shared revenue calculation context
TTL_BUILDS = 600          # 10 minutes - build optimizer results
TTL_HISTORICAL_PRICES = 1800  # 30 minutes - historical price averages

def _redis_kwargs_from_url(url: str) -> dict[str, Any]:
    """Build aiocache Redis kwargs from redis:// or rediss:// URL."""
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    config: dict[str, Any] = {"endpoint": host, "port": port}
    if parsed.password is not None:
        config["password"] = unquote(parsed.password)
    path = (parsed.path or "").strip("/")
    if path.isdigit():
        config["db"] = int(path)
    if parsed.scheme == "rediss":
        config["ssl"] = True
    return config


# Backend selection: unset REDIS_URL locally for in-memory; Docker sets redis://redis:6379/0
CACHE_BACKEND = Cache.MEMORY
REDIS_CONFIG: dict[str, Any] = {}
_redis_url = (os.getenv("REDIS_URL") or "").strip()
if _redis_url:
    _parsed = urlparse(_redis_url)
    if _parsed.scheme in ("redis", "rediss"):
        CACHE_BACKEND = Cache.REDIS
        REDIS_CONFIG = _redis_kwargs_from_url(_redis_url)
        logger.info("Cache configured with Redis backend (%s:%s)", REDIS_CONFIG["endpoint"], REDIS_CONFIG["port"])
    else:
        logger.warning(
            "REDIS_URL is set but is not redis:// or rediss://; using in-memory cache",
        )
else:
    logger.info("Cache configured with in-memory backend")


# --- Cache Key Builders ---

def _is_ignored_key_arg(value: Any) -> bool:
    """Return True for arguments that must not influence cache keys.

    Callables (functions, lambdas, ``functools.partial``, bound methods, classes) and
    modules are injected dependencies, not inputs that change the result. Their repr
    also changes between calls (memory addresses), and a ``partial`` may carry secrets
    such as the Politics & War API key.
    """
    return callable(value) or isinstance(value, types.ModuleType)


def _dumps(value: Any) -> str:
    """Serialize an already-normalized value to canonical JSON."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _stable_value(value: Any) -> Any:
    """Normalize a value into JSON-compatible data that is identical across processes.

    Mapping and set ordering is normalized so equal values give equal keys even with
    hash randomization (Redis is shared by the bot, API and scanner processes).
    """
    if isinstance(value, Enum):
        return {"__enum__": f"{type(value).__module__}.{type(value).__qualname__}.{value.name}"}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if _is_ignored_key_arg(value):
        return "<callable>"
    if isinstance(value, (bytes, bytearray)):
        return {"__bytes__": bytes(value).hex()}
    if isinstance(value, Mapping):
        items = [[_stable_value(k), _stable_value(v)] for k, v in value.items()]
        items.sort(key=_dumps)
        return {"__mapping__": items}
    if isinstance(value, (set, frozenset)):
        return {"__set__": sorted((_stable_value(v) for v in value), key=_dumps)}
    if isinstance(value, tuple):
        return {"__tuple__": [_stable_value(v) for v in value]}
    if isinstance(value, list):
        return [_stable_value(v) for v in value]
    return {"__repr__": [f"{type(value).__module__}.{type(value).__qualname__}", repr(value)]}


def _hash_args(*args: Any, **kwargs: Any) -> str:
    """Hash call arguments into a stable digest, skipping callables and modules.

    Only the digest is returned, so raw argument text (which could contain secrets)
    never ends up in a cache key.
    """
    payload = {
        "args": [_stable_value(arg) for arg in args if not _is_ignored_key_arg(arg)],
        "kwargs": {
            name: _stable_value(value)
            for name, value in kwargs.items()
            if not _is_ignored_key_arg(value)
        },
    }
    return hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:32]


def build_key_from_nation_id(
    func: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> str:
    """Build cache key using nation_id from kwargs or first positional arg."""
    nation_id = kwargs.get("nation_id") or kwargs.get("nationid")
    if nation_id is None and args:
        nation_id = args[0] if isinstance(args[0], (int, str)) else None
    return f"{func.__name__}:{nation_id or 'unknown'}"


def build_key_ignoring_callables(
    func: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> str:
    """Build a cache key from the function identity and its non-callable arguments.

    Key format is ``"<module>.<qualname>:<digest>"``. Callables and modules are skipped,
    so a fresh ``lambda`` or ``partial(call, api_key=...)`` per call still hits the same
    entry and the API key never reaches Redis. If every argument is a callable, all
    calls share one key.
    """
    module = getattr(func, "__module__", None) or ""
    name = getattr(func, "__qualname__", None) or getattr(func, "__name__", "unknown")
    return f"{module}.{name}:{_hash_args(*args, **kwargs)}"


def build_key_from_all_args(
    func: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> str:
    """Build cache key from all arguments; callables and modules are ignored.

    Kept for backwards compatibility; equivalent to build_key_ignoring_callables.
    """
    return build_key_ignoring_callables(func, *args, **kwargs)


# --- Decorator Factories ---

def _cached(namespace: str, ttl: int) -> cached:
    """Create a ``cached`` decorator on the shared backend with callable-safe keys."""
    return cached(
        ttl=ttl,
        cache=CACHE_BACKEND,
        namespace=namespace,
        serializer=PickleSerializer(),
        key_builder=build_key_ignoring_callables,
        **REDIS_CONFIG,
    )


def cache_prices(ttl: int = TTL_PRICES):
    """Cache decorator for trade price fetches."""
    return _cached("prices", ttl)


def cache_game_context(ttl: int = TTL_GAME_DATA):
    """Cache decorator for shared game context (colors, radiation, treasures)."""
    return _cached("game_context", ttl)


def cache_historical_prices(ttl: int = TTL_HISTORICAL_PRICES):
    """Cache decorator for 30-day historical price averages."""
    return _cached("historical_prices", ttl)


def cache_builds(ttl: int = TTL_BUILDS):
    """Cache decorator for build optimizer results."""
    return _cached("builds", ttl)


def cache_revenue_context(ttl: int = TTL_REVENUE_CONTEXT):
    """Cache decorator for revenue calculation context."""
    return _cached("revenue_context", ttl)


# --- Manual Cache Access (for invalidation or direct use) ---

_cache_instance: Optional[Cache] = None


def get_cache() -> Cache:
    """Get the shared cache instance for manual operations."""
    global _cache_instance
    if _cache_instance is None:
        if CACHE_BACKEND == Cache.REDIS:
            _cache_instance = Cache(
                CACHE_BACKEND,
                serializer=PickleSerializer(),
                **REDIS_CONFIG,
            )
        else:
            _cache_instance = Cache(
                CACHE_BACKEND,
                serializer=PickleSerializer(),
            )
    return _cache_instance


async def invalidate_prices() -> None:
    """Manually invalidate all cached prices (e.g., on turn change)."""
    cache = get_cache()
    await cache.clear(namespace="prices")
    await cache.clear(namespace="historical_prices")
    logger.info("Invalidated price caches")


async def invalidate_game_context() -> None:
    """Manually invalidate game context cache."""
    cache = get_cache()
    await cache.clear(namespace="game_context")
    await cache.clear(namespace="revenue_context")
    logger.info("Invalidated game context caches")


async def invalidate_all() -> None:
    """Clear all caches (useful for debugging or major game updates)."""
    cache = get_cache()
    await cache.clear()
    logger.info("Invalidated all caches")


# --- Utility for sync Flask context ---

T = TypeVar("T")


def run_cached_async(coro: Callable[..., T]) -> Callable[..., T]:
    """Wrapper to run async cached functions from sync Flask routes."""
    import asyncio

    @wraps(coro)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro(*args, **kwargs))
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    return wrapper
