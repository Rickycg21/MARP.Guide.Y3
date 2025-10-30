# services/extraction/config.py
import os
import logging
from functools import lru_cache
from dataclasses import dataclass
from urllib.parse import quote, urlsplit, urlunsplit


# ----------------------------
# Env helpers
# ----------------------------
def _env_str(key: str, default: str) -> str:
    val = os.getenv(key)
    return val.strip() if val and val.strip() else default

def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        return default

def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


# ----------------------------
# Logging
# ----------------------------
def setup_logging(level: str) -> None:
    """Configure root + uvicorn loggers once."""
    if getattr(setup_logging, "_configured", False):
        return
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        level=lvl,
    )
    # keep uvicorn loggers aligned
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).setLevel(lvl)
    setup_logging._configured = True


# ----------------------------
# Settings model
# ----------------------------
@dataclass(frozen=True)
class Settings:
    # service identity
    service_name: str
    service_port: int
    log_level: str

    # rabbitmq
    rabbitmq_url: str
    event_exchange: str
    queue_name: str

    # storage
    data_root: str
    pdf_dir: str
    text_dir: str
    metrics_dir: str

    # behavior
    force_reextract: bool


def _build_rabbit_url() -> str:
    """Build AMQP URL from discrete envs; URL-encode creds & vhost."""
    user  = quote(_env_str("RABBITMQ_USER", "guest"))
    pw    = quote(_env_str("RABBITMQ_PASS", "guest"))
    host  = _env_str("RABBITMQ_HOST", "rabbitmq")
    port  = _env_int("RABBITMQ_PORT", 5672)
    vhost = _env_str("RABBITMQ_VHOST", "/")
    path  = "/" if vhost in ("", "/") else "/" + quote(vhost.lstrip("/"))
    return f"amqp://{user}:{pw}@{host}:{port}{path}"


def _mask_url(url: str) -> str:
    """Mask password in a URL for logging."""
    try:
        parts = urlsplit(url)
        if parts.username:
            user = parts.username
            host = parts.hostname or ""
            port = f":{parts.port}" if parts.port else ""
            netloc = f"{user}:****@{host}{port}"
            return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        pass
    return url


def _ensure_dirs(*paths: str) -> None:
    for p in paths:
        os.makedirs(p, exist_ok=True)


# ----------------------------
# Factory (cached)
# ----------------------------
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    service_name = _env_str("SERVICE_NAME", "extraction-service")
    service_port = _env_int("SERVICE_PORT", 8000)
    log_level    = _env_str("LOG_LEVEL", "INFO")

    data_root   = _env_str("DATA_ROOT", "/data")
    pdf_dir     = _env_str("PDF_DIR",   os.path.join(data_root, "pdfs"))
    text_dir    = _env_str("TEXT_DIR",  os.path.join(data_root, "text"))
    metrics_dir = _env_str("METRICS_DIR", os.path.join(data_root, "metrics"))
    _ensure_dirs(pdf_dir, text_dir, metrics_dir)

    # RabbitMQ URL: explicit RABBITMQ_URL wins; else build from parts
    rabbitmq_url = _env_str("RABBITMQ_URL", _build_rabbit_url())
    event_exchange = _env_str("EVENT_EXCHANGE", "events")
    queue_name     = _env_str("QUEUE_NAME", "extraction.doc_fetched")

    force_reextract = _env_bool("FORCE_REEXTRACT", False)

    setup_logging(log_level)
    logging.getLogger(__name__).info(
        "Loaded settings service=%s port=%s data_root=%s pdf_dir=%s text_dir=%s rabbitmq=%s exchange=%s queue=%s",
        service_name, service_port, data_root, pdf_dir, text_dir, _mask_url(rabbitmq_url), event_exchange, queue_name
    )

    return Settings(
        service_name=service_name,
        service_port=service_port,
        log_level=log_level,
        rabbitmq_url=rabbitmq_url,
        event_exchange=event_exchange,
        queue_name=queue_name,
        data_root=data_root,
        pdf_dir=pdf_dir,
        text_dir=text_dir,
        metrics_dir=metrics_dir,
        force_reextract=force_reextract,
    )


# Public singleton
settings = get_settings()
