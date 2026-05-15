"""잡 결과 파일 정리 — M16.

cleanup_old_jobs(reports_jobs_dir, keep_count=50, keep_days=30):
  최근 keep_count개 OR keep_days일 이내 둘 중 더 너그러운 쪽 보존.
  reports/jobs/*.html 대상. 비 .html 파일은 건드리지 않음.
"""

from __future__ import annotations

import time
from pathlib import Path  # noqa: TC003


def cleanup_old_jobs(
    reports_jobs_dir: Path,
    *,
    keep_count: int = 50,
    keep_days: int = 30,
) -> int:
    """잡 결과 HTML 파일 정리. 삭제된 파일 수 반환."""
    if not reports_jobs_dir.exists():
        return 0

    files = sorted(
        reports_jobs_dir.glob("*.html"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not files:
        return 0

    cutoff_ts = time.time() - (keep_days * 86400)

    keep: set[Path] = set()
    for i, f in enumerate(files):
        within_count = i < keep_count
        within_days = f.stat().st_mtime >= cutoff_ts
        if within_count or within_days:
            keep.add(f)

    deleted = 0
    for f in files:
        if f not in keep:
            f.unlink(missing_ok=True)
            deleted += 1

    return deleted
