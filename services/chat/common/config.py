# Centralised configuration and logging setup for all services.

# What this module provides:
#   1) A Settings dataclass holding all env-driven configuration
#   2) get_settings(): reads env vars once, configures logging once
#   3) settings: a module-level singleton (import and use anywhere)

import os        # Access to process environment variables (Docker injects these)
import logging   # Python's standard logging framework
from functools import lru_cache  # Cache get_settings() so we read env only once
from dataclasses import dataclass

# -----------------------------------------------------------------------------
# Settings dataclass (immutable)
# -----------------------------------------------------------------------------
@dataclass(frozen=True) # frozen=True makes the instance read-only after creation
class Settings:
    service_Name: str
    service_Port: int
    rabbitmq_URL: str
    data_Root: str
    log_Level: str # One of: DEBUG, INFO, WARNING, ERROR, CRITICAL

# -----------------------------------------------------------------------------
# Small helpers for robust environment variable parsing
# -----------------------------------------------------------------------------
def _env_str(key: str, default: str) -> str:
    """
    Read a string environment variable & fall back to default if unset or empty
    """
    val = os.getenv(key, default).strip()
    return val if val else default

def _env_int(key: str, default: int) -> int:
    """
    Read an integer environment variable & fall back to default if unset or empty
    """
    raw = os.getenv(key)
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        return default

# -----------------------------------------------------------------------------
# Logging configuration
# -----------------------------------------------------------------------------
def setup_logging(level: str) -> None:
    """
    Configure the root logger ONCE per process (idempotent).
    Guard with a flag (_configured) so repeated imports don't attach duplicate handlers.
    """
    if getattr(setup_logging, "_configured", False):
        return

    # Set up the root logger. All child loggers inherit this.
    logging.basicConfig(
        # Example output:
        # 2025-10-25 12:34:56,789 INFO [config] Loaded settings ...
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        level=getattr(logging, level.upper(), logging.INFO) # Fallback to INFO on bad input
    )

    # Mark as configured so subsequent calls do nothing
    setup_logging._configured = True

# -----------------------------------------------------------------------------
# Read and cache settings once
# -----------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Read all environment variables, configure logging once, and return a
    frozen Settings object.
    """
    # Read from environment using helpers with safe fallbacks
    service_name = _env_str("SERVICE_NAME", "unknown-service")
    service_port = _env_int("SERVICE_PORT", 8000)
    rabbitmq_url = _env_str("RABBITMQ_URL", "amqp://${RABBITMQ_USER:-admin}:${RABBITMQ_PASS:-admin}@rabbitmq:5672/")
    data_root    = _env_str("DATA_ROOT", "/data")
    log_level    = _env_str("LOG_LEVEL", "INFO")

    # Configure logging
    setup_logging(log_level)
    # Log a concise startup summary following the configured format
    # Output: %(asctime)s INFO [config] Loaded settings ...
    logging.getLogger("config").info(
        "Loaded settings service=%s port=%s data_root=%s rabbitmq=%s",
        service_name, service_port, data_root, rabbitmq_url
    )

    # Build and return an immutable Settings object
    return Settings(
        service_Name=service_name,
        service_Port=service_port,
        rabbitmq_URL=rabbitmq_url,
        data_Root=data_root,
        log_Level=log_level,
    )

# -----------------------------------------------------------------------------
# Public, module-level singleton
# -----------------------------------------------------------------------------
# Import this from anywhere in your service: from common.config import settings
# This triggers get_settings() once (per process) and reuses it afterwards.
settings = get_settings()