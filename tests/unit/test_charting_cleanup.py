"""cleanup_old_charts — 단위 테스트."""

from __future__ import annotations

import os
import time
from datetime import timedelta
from pathlib import Path

from signal_program.charting.cleanup import cleanup_old_charts


def _write_png(path: Path, name: str, age_seconds: float) -> Path:
    f = path / name
    f.write_bytes(b"\x89PNG\r\n\x1a\n")
    old_mtime = time.time() - age_seconds
    os.utime(f, (old_mtime, old_mtime))
    return f


def test_removes_files_older_than_max_age(tmp_path: Path) -> None:
    _write_png(tmp_path, "new1.png", 23 * 3600)
    _write_png(tmp_path, "new2.png", 23 * 3600)
    _write_png(tmp_path, "new3.png", 23 * 3600)
    _write_png(tmp_path, "old1.png", 25 * 3600)
    _write_png(tmp_path, "old2.png", 25 * 3600)

    removed = cleanup_old_charts(tmp_path, timedelta(hours=24))

    assert removed == 2
    remaining = list(tmp_path.glob("*.png"))
    assert len(remaining) == 3
    assert all("new" in f.name for f in remaining)


def test_missing_dir_returns_zero() -> None:
    assert cleanup_old_charts(Path("/nonexistent/path"), timedelta(hours=1)) == 0


def test_empty_dir_returns_zero(tmp_path: Path) -> None:
    assert cleanup_old_charts(tmp_path) == 0


def test_ignores_non_png_files(tmp_path: Path) -> None:
    (tmp_path / "old.json").write_text("{}")
    os.utime(tmp_path / "old.json", (0, 0))
    removed = cleanup_old_charts(tmp_path, timedelta(hours=1))
    assert removed == 0
