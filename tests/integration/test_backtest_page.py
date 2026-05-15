"""백테스트 페이지 통합 테스트 — M15 Phase 1 RED."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ── 픽스처 ───────────────────────────────────────────────────────────────────


def _noop_executor(spec: object, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("<html><body>backtest report</body></html>", encoding="utf-8")


@pytest.fixture
def client(tmp_path: Path):  # type: ignore[no-untyped-def]
    from signal_program.web.app import create_app

    app = create_app(
        settings_path=tmp_path / "settings.json",
        reports_dir=tmp_path / "reports",
        candles_cache_root=tmp_path / "candles",
        _job_executor=_noop_executor,
    )
    with TestClient(app) as c:
        yield c


# ── 페이지 HTML ───────────────────────────────────────────────────────────────


def test_get_backtest_page_returns_html(client: TestClient) -> None:
    resp = client.get("/backtest")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "<html" in resp.text


def test_backtest_html_has_simple_mode_form(client: TestClient) -> None:
    resp = client.get("/backtest")
    html = resp.text
    assert "market" in html
    assert "period_from" in html
    assert "period_to" in html
    assert "mode" in html


def test_backtest_html_has_advanced_collapsed_section(client: TestClient) -> None:
    resp = client.get("/backtest")
    html = resp.text
    assert "train_months" in html
    assert "grid_str" in html


def test_backtest_html_no_external_cdn(client: TestClient) -> None:
    import re

    resp = client.get("/backtest")
    assert "cdn." not in resp.text
    external = re.findall(r'(?:href|src)=["\']https://', resp.text)
    assert len(external) == 0


def test_backtest_html_no_optimal_or_recommended_copy(client: TestClient) -> None:
    resp = client.get("/backtest")
    html = resp.text.lower()
    for banned in ["추천", "최적", "알파"]:
        assert banned not in html, f"금지 문구 발견: {banned!r}"


# ── API 라우트 ────────────────────────────────────────────────────────────────


def test_post_job_returns_202_with_job_view(client: TestClient) -> None:
    resp = client.post(
        "/api/backtest/jobs",
        json={"market": "KRW-BTC", "period_from": "2025-01-01", "period_to": "2025-02-01"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "queued"


def test_post_job_returns_422_korean_when_invalid_period(client: TestClient) -> None:
    resp = client.post(
        "/api/backtest/jobs",
        json={"market": "KRW-BTC", "period_from": "2025-02-01", "period_to": "2025-01-01"},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    messages = [e.get("message", "") for e in detail if isinstance(e, dict)]
    assert any("이후" in m or "period" in m.lower() or "기간" in m for m in messages)


def test_post_job_returns_429_when_queue_full(tmp_path: Path) -> None:
    import time as _time
    import tempfile
    from pathlib import Path as _Path

    from signal_program.web.app import create_app
    from signal_program.web.jobs import BacktestJobManager

    def slow_executor(spec: object, output_path: _Path) -> None:
        _time.sleep(30)

    with tempfile.TemporaryDirectory() as td:
        tmp = _Path(td)
        app = create_app(
            settings_path=tmp / "settings.json",
            reports_dir=tmp / "reports",
            candles_cache_root=tmp / "candles",
            _job_executor=slow_executor,
        )
        with TestClient(app) as c:
            for _ in range(BacktestJobManager.MAX_QUEUE_LEN):
                r = c.post(
                    "/api/backtest/jobs",
                    json={"market": "KRW-BTC", "period_from": "2025-01-01", "period_to": "2025-02-01"},
                )
                assert r.status_code == 202
            r = c.post(
                "/api/backtest/jobs",
                json={"market": "KRW-BTC", "period_from": "2025-01-01", "period_to": "2025-02-01"},
            )
            assert r.status_code == 429
            assert "잡 큐가 가득 찼습니다" in r.json().get("detail", {}).get("message", "")


def test_get_jobs_returns_array_sorted_by_submitted_desc(client: TestClient) -> None:
    client.post(
        "/api/backtest/jobs",
        json={"market": "KRW-BTC", "period_from": "2025-01-01", "period_to": "2025-02-01"},
    )
    client.post(
        "/api/backtest/jobs",
        json={"market": "KRW-ETH", "period_from": "2025-01-01", "period_to": "2025-02-01"},
    )
    resp = client.get("/api/backtest/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    assert isinstance(jobs, list)
    if len(jobs) >= 2:
        from datetime import datetime

        t0 = datetime.fromisoformat(jobs[0]["submitted_at"])
        t1 = datetime.fromisoformat(jobs[1]["submitted_at"])
        assert t0 >= t1


def test_get_job_by_id_returns_full_view(client: TestClient) -> None:
    resp = client.post(
        "/api/backtest/jobs",
        json={"market": "KRW-BTC", "period_from": "2025-01-01", "period_to": "2025-02-01"},
    )
    job_id = resp.json()["job_id"]
    resp2 = client.get(f"/api/backtest/jobs/{job_id}")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["job_id"] == job_id
    assert "status" in data
    assert "market" in data


def test_get_job_report_serves_html_file_for_succeeded_job(client: TestClient) -> None:
    resp = client.post(
        "/api/backtest/jobs",
        json={"market": "KRW-BTC", "period_from": "2025-01-01", "period_to": "2025-02-01"},
    )
    job_id = resp.json()["job_id"]
    for _ in range(40):
        time.sleep(0.1)
        r = client.get(f"/api/backtest/jobs/{job_id}")
        if r.json().get("status") == "succeeded":
            break
    report_resp = client.get(f"/api/backtest/jobs/{job_id}/report")
    assert report_resp.status_code == 200
    assert "text/html" in report_resp.headers["content-type"]


def test_post_walkforward_job_in_advanced_mode_queues_walkforward_kind(
    client: TestClient,
) -> None:
    resp = client.post(
        "/api/backtest/jobs",
        json={
            "kind": "walkforward",
            "market": "KRW-BTC",
            "period_from": "2025-01-01",
            "period_to": "2025-02-01",
            "train_months": 8,
            "validate_months": 2,
            "grid_str": "bb_std_mult:1.5,2.0",
        },
    )
    assert resp.status_code == 202
    assert resp.json()["kind"] == "walkforward"
