"""job_retention 단위 테스트 — M16 Phase 1 RED."""
from __future__ import annotations

from pathlib import Path

from signal_program.state.job_retention import cleanup_old_jobs


def _make_html(jobs_dir: Path, name: str, mtime_offset_days: int = 0) -> Path:
    import os
    import time

    p = jobs_dir / f"{name}.html"
    p.write_text("<html>test</html>", encoding="utf-8")
    if mtime_offset_days:
        new_mtime = time.time() - (mtime_offset_days * 86400)
        os.utime(p, (new_mtime, new_mtime))
    return p


def test_cleanup_keeps_latest_n_files(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "reports" / "jobs"
    jobs_dir.mkdir(parents=True)
    for i in range(60):
        # mtime_offset_days=i+1: 모두 1일 이상 오래된 파일 (days 정책 적용 안 됨)
        _make_html(jobs_dir, f"job_{i:03d}", mtime_offset_days=i + 1)
    # keep_days=0: 오늘 이후만 days 보호 → 모든 파일이 1일+ 오래됨 → count 정책만 적용
    deleted = cleanup_old_jobs(jobs_dir, keep_count=50, keep_days=0)
    remaining = list(jobs_dir.glob("*.html"))
    assert deleted == 10
    assert len(remaining) == 50


def test_cleanup_keeps_recent_n_days(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "reports" / "jobs"
    jobs_dir.mkdir(parents=True)
    for i in range(5):
        _make_html(jobs_dir, f"new_{i}", mtime_offset_days=i)
    for i in range(5):
        _make_html(jobs_dir, f"old_{i}", mtime_offset_days=35 + i)
    deleted = cleanup_old_jobs(jobs_dir, keep_count=1, keep_days=30)
    assert all((jobs_dir / f"new_{i}.html").exists() for i in range(5))
    assert deleted == 5


def test_cleanup_takes_more_lenient_of_two_policies(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "reports" / "jobs"
    jobs_dir.mkdir(parents=True)
    for i in range(60):
        _make_html(jobs_dir, f"job_{i:03d}", mtime_offset_days=i % 10)
    deleted = cleanup_old_jobs(jobs_dir, keep_count=50, keep_days=30)
    remaining = list(jobs_dir.glob("*.html"))
    assert len(remaining) == 60
    assert deleted == 0


def test_cleanup_returns_deleted_count(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "reports" / "jobs"
    jobs_dir.mkdir(parents=True)
    for i in range(10):
        _make_html(jobs_dir, f"job_{i}", mtime_offset_days=i + 40)
    deleted = cleanup_old_jobs(jobs_dir, keep_count=5, keep_days=30)
    assert deleted == 5


def test_cleanup_ignores_non_job_files(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "reports" / "jobs"
    jobs_dir.mkdir(parents=True)
    for i in range(60):
        _make_html(jobs_dir, f"job_{i:03d}", mtime_offset_days=i + 1)
    txt_file = jobs_dir / "metadata.txt"
    txt_file.write_text("keep me", encoding="utf-8")
    cleanup_old_jobs(jobs_dir, keep_count=50, keep_days=1)
    assert txt_file.exists()


def test_cleanup_handles_empty_directory(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "reports" / "jobs"
    jobs_dir.mkdir(parents=True)
    deleted = cleanup_old_jobs(jobs_dir, keep_count=50, keep_days=30)
    assert deleted == 0


def test_cleanup_handles_missing_directory(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "nonexistent" / "jobs"
    deleted = cleanup_old_jobs(jobs_dir, keep_count=50, keep_days=30)
    assert deleted == 0
