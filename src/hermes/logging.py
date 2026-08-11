from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from loguru import logger


def _domain_filter(domain: str) -> Callable[[dict], bool]:
    return lambda record: record["extra"].get("domain") == domain


def configure_logging(log_dir: Path | None = None, level: str = "INFO") -> None:
    logger.remove()

    logger.add(sys.stderr, level=level)

    if log_dir is None:
        return

    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_dir / "state.jsonl",
        serialize=True,
        enqueue=True,
        rotation="50 MB",
        retention="90 days",
        filter=_domain_filter("state"),
    )
    logger.add(
        log_dir / "acquisition.serval.jsonl",
        serialize=True,
        enqueue=True,
        rotation="100 MB",
        retention="90 days",
        filter=lambda record: (
            record["extra"].get("domain") == "acquisition"
            and record["extra"].get("backend") == "serval"
        ),
    )
    logger.add(
        log_dir / "analysis.jsonl",
        serialize=True,
        enqueue=True,
        rotation="100 MB",
        retention="90 days",
        filter=_domain_filter("analysis"),
    )
