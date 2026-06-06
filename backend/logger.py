"""
Central logging configuration for DPA backend.
Import get_logger(name) in every module instead of using print().
Logs go to both console and a rotating file at logs/dpa_backend.log
"""

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR  = os.path.join(os.path.dirname(__file__), "logs")
LOG_FILE = os.path.join(LOG_DIR, "dpa_backend.log")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

_configured = False


def _configure():
    global _configured
    if _configured:
        return
    _configured = True

    os.makedirs(LOG_DIR, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(fmt)

    # Rotating file handler (5 MB × 5 files)
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)
    root.addHandler(console)
    root.addHandler(file_handler)

    # Quiet noisy third-party libs
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(name)
