"""오래된 차트 PNG 정리 — DESIGN.md §5.4 (24h 자동 정리)."""

from __future__ import annotations

import time
from datetime import timedelta
from pathlib import Path  # noqa: TC003

import structlog

log = structlog.get_logger()

_DEFAULT_MAX_AGE = timedelta(hours=24)


def cleanup_old_charts(
    dir: Path,
    max_age: timedelta = _DEFAULT_MAX_AGE,
) -> int:
    """dir 안의 .png 파일 중 max_age보다 오래된 것을 삭제.

    Args:
        dir: 차트 디렉토리 경로
        max_age: 보존 기간 (기본 24h)

    Returns:
        삭제된 파일 수
    """
    if not dir.exists():
        return 0

    cutoff = time.time() - max_age.total_seconds()
    removed = 0

    for png in dir.glob("*.png"):
        try:
            if png.stat().st_mtime < cutoff:
                png.unlink()
                removed += 1
        except OSError:
            log.warning("chart_cleanup_skip", file=str(png))

    log.info("chart_cleanup", removed_count=removed, dir=str(dir))
    return removed
