"""Opt-in, deterministic pipeline diagnostics."""

import logging
import os


logger = logging.getLogger("pipeline.debug")


def enabled() -> bool:
    return os.getenv("DEBUG_PIPELINE", "").strip().lower() in {"1", "true", "yes", "on"}


def log(section: str, message: str) -> None:
    if enabled():
        logger.info("[DEBUG_PIPELINE] %s | %s", section, message)
