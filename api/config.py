"""
API Configuration Module

This module contains configuration settings for the Flask API,
including security settings for token-based authentication.
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


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    CORS_ORIGINS = ["*"]  # Allow all origins in development


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    # In production, ensure SECRET_KEY is set via environment variable
    SECRET_KEY = os.getenv("SECRET_KEY", "")
    
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
