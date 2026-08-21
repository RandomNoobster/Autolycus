"""
Shared application configuration.

This module is intentionally outside `api/` so domain/infrastructure layers
can access environment-backed configuration without importing delivery code.
"""
import os
from datetime import timedelta
from typing import Optional


def _int_env(name: str, default: int, *, min_v: int = 1, max_v: int = 400) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(min_v, min(int(str(raw).strip(), 10), max_v))
    except ValueError:
        return default

# Public URLs for Discord bot links and bot -> API HTTP calls.
# No trailing slash. AUTOLYCUS_API_BASE_URL is origin only (not .../api); callers append /api/...
AUTOLYCUS_WEB_BASE_URL: str = (
    (os.getenv("AUTOLYCUS_WEB_BASE_URL") or "http://localhost:5173").rstrip("/")
)
AUTOLYCUS_API_BASE_URL: str = (
    (os.getenv("AUTOLYCUS_API_BASE_URL") or "http://localhost:5000").rstrip("/")
)


class Config:
    """Base configuration class."""

    # Flask settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", os.urandom(32).hex())
    DEBUG: bool = False
    TESTING: bool = False

    # Discord OAuth: how long the signed session cookie stays valid (browser Max-Age).
    # Set session.permanent in the OAuth callback so Flask applies this reliably.
    SESSION_LIFETIME_DAYS: int = _int_env("SESSION_LIFETIME_DAYS", 90, min_v=1, max_v=400)
    PERMANENT_SESSION_LIFETIME: timedelta = timedelta(days=SESSION_LIFETIME_DAYS)

    # Token settings (signed links / Bearer tokens from the bot — separate from OAuth cookie)
    TOKEN_MAX_AGE: int = _int_env(
        "TOKEN_MAX_AGE_SEC",
        3600 * 24 * 7,
        min_v=60,
        max_v=3600 * 24 * 400,
    )
    TOKEN_SALT: str = "autolycus-ephemeral-link"
    AUTH_TOKEN_API_KEY: str = os.getenv("AUTH_TOKEN_API_KEY", "")
    DISCORD_BOT_API_KEY: str = os.getenv("DISCORD_BOT_API_KEY", "")
    DISCORD_CLIENT_ID: str = os.getenv("DISCORD_CLIENT_ID", "")
    DISCORD_CLIENT_SECRET: str = os.getenv("DISCORD_CLIENT_SECRET", "")
    DISCORD_REDIRECT_URI: str = os.getenv("DISCORD_REDIRECT_URI", "")
    AUTOLYCUS_WEB_BASE_URL: str = AUTOLYCUS_WEB_BASE_URL

    # CORS settings
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]

    # MongoDB settings
    MONGO_URI: Optional[str] = os.getenv("MONGO_URI")
    MONGO_DB: str = os.getenv("MONGO_DB", "main")

    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 5000
    WAITRESS_THREADS: int = int(os.getenv("WAITRESS_THREADS", 8))
    WAITRESS_CONNECTION_LIMIT: int = int(os.getenv("WAITRESS_CONNECTION_LIMIT", 200))
    WAITRESS_CHANNEL_TIMEOUT: int = int(os.getenv("WAITRESS_CHANNEL_TIMEOUT", 30))

    # Request limits (DoS protection)
    MAX_CONTENT_LENGTH: int = 1 * 1024 * 1024  # 1 MB max request body

    # Security headers
    SECURITY_HEADERS_ENABLED: bool = True
    # Trust proxy headers (X-Forwarded-For/Proto) when behind a reverse proxy
    TRUST_PROXY_HEADERS: bool = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"

    # Session cookie hardening (even if not used)
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"

    # Politics & War API key (raids revenue pre-calc, etc.)
    API_KEY: str = os.getenv("API_KEY", "")


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
    CORS_ORIGINS = ["*"]  # Allow all origins in development
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False
    SECRET_KEY = os.getenv("SECRET_KEY", "")
    SESSION_COOKIE_SECURE = True

    @classmethod
    def validate(cls) -> None:
        """Validate production configuration."""
        if not cls.SECRET_KEY:
            raise ValueError("SECRET_KEY environment variable must be set in production")


def get_config() -> Config:
    """Get the appropriate configuration based on environment."""
    env = os.getenv("FLASK_ENV", "development")
    if env == "production":
        ProductionConfig.validate()
        return ProductionConfig()
    return DevelopmentConfig()
