"""
Shared application configuration.

This module is intentionally outside `api/` so domain/infrastructure layers
can access environment-backed configuration without importing delivery code.
"""
import os
from typing import Optional


class Config:
    """Base configuration class."""

    # Flask settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", os.urandom(32).hex())
    DEBUG: bool = False
    TESTING: bool = False

    # Token settings
    TOKEN_MAX_AGE: int = 3600 * 24 * 7  # 7 days in seconds
    TOKEN_SALT: str = "autolycus-ephemeral-link"
    AUTH_TOKEN_API_KEY: str = os.getenv("AUTH_TOKEN_API_KEY", "")
    DISCORD_BOT_API_KEY: str = os.getenv("DISCORD_BOT_API_KEY", "")

    # CORS settings
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]

    # MongoDB settings
    MONGO_URI: Optional[str] = os.getenv("pymongolink")
    MONGO_DB: str = os.getenv("version", "autolycus")

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
    API_KEY: str = os.getenv("api_key", "")


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
    CORS_ORIGINS = ["*"]  # Allow all origins in development


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
