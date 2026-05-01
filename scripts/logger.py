"""
Centralized logging for the APK update pipeline.

A single log file per pipeline run is shared across all modules.
Console output respects DEBUG_MODE env var; file always captures DEBUG.
"""
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

# ── State (module-level singletons) ──────────────────────────────────────────
_initialized: bool = False
_log_file_path: str = ""


def _ensure_initialized() -> None:
    """Initialize root logger once. Subsequent calls are no-ops."""
    global _initialized, _log_file_path

    if _initialized:
        return

    debug = os.environ.get("DEBUG_MODE", "false").lower() == "true"
    console_level = logging.DEBUG if debug else logging.INFO

    # Create logs directory
    Path("logs").mkdir(exist_ok=True)
    _log_file_path = (
        f"logs/run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.log"
    )

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)-20s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(console_level)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # File handler (always full debug)
    fh = logging.FileHandler(_log_file_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Silence noisy third-party loggers
    for lib in ("androguard", "pyaxmlparser", "urllib3", "requests"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.  Initializes the logging system on first call."""
    _ensure_initialized()
    return logging.getLogger(name)
