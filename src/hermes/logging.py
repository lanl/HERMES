from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from loguru import logger


def _domain_filter(domain: str) -> Callable[[dict], bool]:
    return lambda record: record["extra"].get("domain") == domain


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()

    logger.add(
        log_dir / "state.jsonl",
        serialize=True,
        enqueue=True,
        rotation="50 MB",
        retention="90 days",
        filter=_domain_filter("state"),
    )
    logger.add(
        log_dir / "workflow.jsonl",
        serialize=True,
        enqueue=True,
        rotation="50 MB",
        retention="90 days",
        filter=_domain_filter("workflow"),
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
