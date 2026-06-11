"""Structured logging configuration for Crop Intelligence Agent.

Uses structlog for JSON-formatted logs that are machine-readable and
human-friendly. Every layer of the system uses this configuration.

Log files:
    - crop_agent/logs/agent.log       — all layers combined
    - crop_agent/logs/ingestion.log   — Layer 1 only
    - crop_agent/logs/engineering.log — Layer 2 only
    - crop_agent/logs/ml.log          — Layer 3 only
    - crop_agent/logs/prediction.log  — Layer 4 only

All logs rotate at 10 MB, keeping the last 5 backups.
"""

import logging
import logging.handlers
from pathlib import Path

import structlog

from crop_agent.config.settings import LOG_DIR, LOG_LEVEL

# Maximum log file size before rotation (bytes)
LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB

# Number of backup log files to keep after rotation
LOG_BACKUP_COUNT: int = 5


def _create_rotating_handler(log_file: Path) -> logging.handlers.RotatingFileHandler:
    """Create a rotating file handler for a given log file path.

    Args:
        log_file: Path to the log file to write to.

    Returns:
        A configured RotatingFileHandler that writes JSON logs.
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        filename=str(log_file),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def configure_logging() -> None:
    """Configure structlog for the entire application.

    Must be called once at application startup before any logging occurs.
    After this call, all modules can use structlog.get_logger() directly.

    Sets up:
        - JSON renderer for production (APP_ENV != 'development')
        - Human-readable renderer for development
        - Rotating file handlers per layer
        - Console output at the configured log level
    """
    numeric_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

    # Shared processors applied to every log event
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Root formatter — JSON for production, colored console for development
    import os

    if os.environ.get("APP_ENV", "development") == "development":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    # Console handler — always present
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(numeric_level)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    root_logger.addHandler(console_handler)

    # Layer-specific file handlers
    _log_files: dict[str, str] = {
        "crop_agent.ingestion": "ingestion.log",
        "crop_agent.engineering": "engineering.log",
        "crop_agent.ml": "ml.log",
        "crop_agent.prediction": "prediction.log",
        "crop_agent.scheduler": "agent.log",
        "crop_agent.dashboard": "dashboard.log",
    }

    for logger_name, log_filename in _log_files.items():
        layer_logger = logging.getLogger(logger_name)
        layer_logger.addHandler(_create_rotating_handler(LOG_DIR / log_filename))

    # Master log — catches everything
    root_logger.addHandler(_create_rotating_handler(LOG_DIR / "master.log"))


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger for the given module name.

    This is the only way to get a logger in this codebase.
    Use it like: logger = get_logger(__name__)

    Args:
        name: The module name, typically __name__.

    Returns:
        A bound structlog logger configured per the application settings.
    """
    return structlog.get_logger(name)
