"""
Application Configuration Settings
----------------------------------
Uses pydantic-settings to validate and parse environment variables.
"""

import socket
import logging
from typing import List, Union, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("meterflow.config")


def resolve_host_fallback(hostname: str) -> Optional[str]:
    """
    Attempts to resolve hostname using the standard system resolver.
    If the local system/router DNS fails (e.g. [Errno 11001] or 'Query refused'),
    falls back to trusted public DNS servers (8.8.8.8, 1.1.1.1) via dnspython.
    """
    if not hostname or hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return None
    try:
        socket.getaddrinfo(hostname, None)
        return None  # System DNS works normally
    except socket.gaierror:
        # System DNS failed or router refused query. Use fallback public DNS.
        try:
            import dns.resolver
            resolver = dns.resolver.Resolver()
            resolver.nameservers = ["8.8.8.8", "1.1.1.1", "9.9.9.9"]
            resolver.timeout = 2.5
            resolver.lifetime = 2.5
            answers = resolver.resolve(hostname, "A")
            if answers:
                ip = str(answers[0])
                logger.info(f"Local system DNS failed for '{hostname}'; automatically resolved via public DNS to {ip}")
                return ip
        except Exception as exc:
            logger.warning(f"Could not resolve '{hostname}' via fallback public DNS: {exc}")
            return None
    return None


class Settings(BaseSettings):
    # Application metadata
    APP_NAME: str = "MeterFlow"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = Field(default="development", description="Current environment (development, staging, production)")
    DEBUG: bool = False
    LOG_LEVEL: str = "info"

    # Server binding
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # PostgreSQL Database URL
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/meterflow",
        description="Database connection string",
    )

    # Database Pool Settings
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800  # Recycle connections after 30 minutes

    # CORS Configuration
    CORS_ORIGINS: Union[str, List[str]] = "http://localhost:3000,http://127.0.0.1:3000"

    # Authentication & Security
    JWT_SECRET_KEY: str = Field(
        default="meterflow-super-secret-jwt-key-for-local-development-change-in-prod-xyz123",
        description="Secret key for signing JWT tokens",
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Redis & Rate Limiting Settings
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string for distributed caching & rate limiting",
    )
    RATE_LIMIT_ALGORITHM: str = Field(
        default="sliding_window",
        description="Rate limiting algorithm: 'sliding_window' or 'token_bucket'",
    )
    DEFAULT_RATE_LIMIT_PER_MINUTE: int = 60
    DEFAULT_RATE_LIMIT_WINDOW_SECONDS: int = 60
    DEFAULT_BURST_CAPACITY: int = 10

    # Razorpay Payment Gateway (Test Mode)
    RAZORPAY_KEY_ID: str = Field(
        default="rzp_test_placeholder_key_id",
        description="Razorpay API Key ID (Test Mode)",
    )
    RAZORPAY_KEY_SECRET: str = Field(
        default="rzp_test_placeholder_key_secret",
        description="Razorpay API Key Secret (Test Mode)",
    )
    RAZORPAY_WEBHOOK_SECRET: str = Field(
        default="rzp_test_placeholder_webhook_secret",
        description="Razorpay Webhook Secret for HMAC-SHA256 signature verification",
    )

    # Security Hardening & Rate Limiting
    ENABLE_HSTS: bool = Field(
        default=False,
        description="Enable Strict-Transport-Security header (only for HTTPS deployments)",
    )
    TRUSTED_PROXIES: Union[str, List[str]] = Field(
        default="",
        description="Comma-separated list of trusted upstream reverse proxy IP addresses",
    )
    AUTH_RATE_LIMIT_PER_MINUTE: int = Field(
        default=10,
        description="Max allowed requests per minute for public authentication routes (/auth/login, /auth/register)",
    )

    # Isolated Test Database
    TEST_DATABASE_URL: Optional[str] = Field(
        default=None,
        description="Dedicated test database connection string to isolate tests from development data",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("DATABASE_URL", "TEST_DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Optional[str]) -> Optional[str]:
        """
        Ensures the SQLAlchemy driver prefix is postgresql+psycopg:// for psycopg 3.
        Supports standard postgresql:// and postgres:// connection strings from providers like Neon.
        """
        if not v:
            return v
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+psycopg://", 1)
        elif v.startswith("postgresql://") and not v.startswith("postgresql+"):
            v = v.replace("postgresql://", "postgresql+psycopg://", 1)

        # Resilient DNS fallback: if local router DNS fails, resolve via public DNS
        if "hostaddr=" not in v and "@" in v:
            try:
                after_at = v.split("@", 1)[1]
                host_part = after_at.split("/", 1)[0]
                host = host_part.split(":", 1)[0] if ":" in host_part else host_part
                fallback_ip = resolve_host_fallback(host)
                if fallback_ip:
                    sep = "&" if "?" in v else "?"
                    v = f"{v}{sep}hostaddr={fallback_ip}"
            except Exception:
                pass

        return v

    @property
    def cors_origins_list(self) -> List[str]:
        if isinstance(self.CORS_ORIGINS, list):
            return self.CORS_ORIGINS
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def trusted_proxies_list(self) -> List[str]:
        if isinstance(self.TRUSTED_PROXIES, list):
            return self.TRUSTED_PROXIES
        return [ip.strip() for ip in self.TRUSTED_PROXIES.split(",") if ip.strip()]


# Global cached settings instance
settings = Settings()
