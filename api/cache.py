"""
Caching configuration for Autolycus API.

Uses aiocache for async-compatible memoization with TTL support.
Cache strategy: Cache expensive logic/computation functions, NOT API routes.

Design Principles:
    - Cache shared game data (prices, colors, radiation, treasures)
    - Cache expensive per-nation calculations
    - Do NOT cache API routes (they need user context and filters)
    - Use in-memory cache for development, optionally Redis for production
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

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

# Backend selection - can switch to Redis in production
CACHE_BACKEND = Cache.MEMORY

# Optional Redis configuration (used when REDIS_URL is set)
REDIS_CONFIG: dict[str, Any] = {}
if os.getenv("REDIS_URL"):
    CACHE_BACKEND = Cache.REDIS
    REDIS_CONFIG = {
        "endpoint": os.getenv("REDIS_HOST", "localhost"),
        "port": int(os.getenv("REDIS_PORT", 6379)),
        "password": os.getenv("REDIS_PASSWORD"),
    }
    logger.info("Cache configured with Redis backend")
else:
    logger.info("Cache configured with in-memory backend")


# --- Cache Key Builders ---

def _hash_args(*args: Any, **kwargs: Any) -> str:
    """Create a hash key from function arguments."""
    key_data = json.dumps(
        {"args": [str(a) for a in args], "kwargs": {k: str(v) for k, v in sorted(kwargs.items())}},
        sort_keys=True,
    )
    return hashlib.md5(key_data.encode()).hexdigest()[:16]


def build_key_from_nation_id(
    func: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> str:
    """Build cache key using nation_id from kwargs or first positional arg."""
    nation_id = kwargs.get("nation_id") or kwargs.get("nationid")
    if nation_id is None and args:
        # Try to extract from first positional argument
        nation_id = args[0] if isinstance(args[0], (int, str)) else None
    return f"{func.__name__}:{nation_id or 'unknown'}"


def build_key_from_all_args(
    func: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> str:
    """Build cache key from all arguments (for functions with complex params)."""
    return f"{func.__name__}:{_hash_args(*args, **kwargs)}"


# --- Decorator Factories ---

def cache_prices(ttl: int = TTL_PRICES):
    """
    Cache decorator for trade price fetches.
    
    Use this for functions that fetch current market prices from P&W API.
    Prices update roughly hourly, so 5-minute TTL reduces API calls while
    keeping data reasonably fresh.
    """
    return cached(
        ttl=ttl,
        cache=CACHE_BACKEND,
        namespace="prices",
        serializer=PickleSerializer(),
        **REDIS_CONFIG,
    )


def cache_game_context(ttl: int = TTL_GAME_DATA):
    """
    Cache decorator for shared game context (colors, radiation, treasures).
    
    This data changes slowly and is shared across all requests, making it
    an ideal caching target. Used by revenue calculations.
    """
    return cached(
        ttl=ttl,
        cache=CACHE_BACKEND,
        namespace="game_context",
        serializer=PickleSerializer(),
        **REDIS_CONFIG,
    )


def cache_historical_prices(ttl: int = TTL_HISTORICAL_PRICES):
    """
    Cache decorator for 30-day historical price averages.
    
    Historical averages don't change rapidly, so longer TTL is appropriate.
    """
    return cached(
        ttl=ttl,
        cache=CACHE_BACKEND,
        namespace="historical_prices",
        serializer=PickleSerializer(),
        **REDIS_CONFIG,
    )


def cache_builds(ttl: int = TTL_BUILDS):
    """
    Cache decorator for build optimizer results.
    
    Build calculations are expensive but deterministic for the same inputs.
    Cache by all parameters (infra, land, mmr, continent, etc.)
    """
    return cached(
        ttl=ttl,
        cache=CACHE_BACKEND,
        namespace="builds",
        serializer=PickleSerializer(),
        key_builder=build_key_from_all_args,
        **REDIS_CONFIG,
    )


def cache_revenue_context(ttl: int = TTL_REVENUE_CONTEXT):
    """
    Cache decorator for revenue calculation context.
    
    Caches the shared data needed for revenue calculations:
    colors, prices, treasures, radiation, seasonal modifiers.
    """
    return cached(
        ttl=ttl,
        cache=CACHE_BACKEND,
        namespace="revenue_context",
        serializer=PickleSerializer(),
        **REDIS_CONFIG,
    )


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
    """
    Wrapper to run async cached functions from sync Flask routes.
    
    Usage:
        result = run_cached_async(get_cached_prices)()
    """
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
