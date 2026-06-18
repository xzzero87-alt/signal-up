"""GET /api/logs — 로그 tail 엔드포인트 (BUG-4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from signal_program.web.app import create_app

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def make_client(tmp_path: Path):  # type: ignore[no-untyped-def]
    def _make(log_path: Path | None) -> TestClient:
        app = create_app(
            settings_path=tmp_path / "settings.json",
            reports_dir=tmp_path / "reports",
            candles_cache_root=tmp_path / "candles",
            logs_path=log_path if log_path is not None else tmp_path / "absent.log",
        )
        return TestClient(app)

    return _make


def test_logs_returns_empty_list_when_file_absent(make_client) -> None:  # type: ignore[no-untyped-def]
    with make_client(None) as c:
        resp = c.get("/api/logs")
        assert resp.status_code == 200
        assert resp.json() == []


def test_logs_returns_tail_in_order(make_client, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = tmp_path / "daemon.log"
    log.write_text("\n".join(f"line{i}" for i in range(1, 11)) + "\n", encoding="utf-8")
    with make_client(log) as c:
        resp = c.get("/api/logs?limit=3")
        assert resp.status_code == 200
        assert resp.json() == ["line8", "line9", "line10"]


def test_logs_limit_is_bounded(make_client) -> None:  # type: ignore[no-untyped-def]
    with make_client(None) as c:
        assert c.get("/api/logs?limit=0").status_code == 422
        assert c.get("/api/logs?limit=99999").status_code == 422
