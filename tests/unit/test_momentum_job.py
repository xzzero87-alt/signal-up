"""momentum/job.py 오케스트레이션 테스트 (ADR-0031) — Notifier mock, 알림 포맷 스냅샷."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from signal_program.config import Settings
from signal_program.momentum.job import _MAX_FETCH_ATTEMPTS_PER_DAY, MomentumJob

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.anyio

_KST = ZoneInfo("Asia/Seoul")
_POOL_CODES = ["005930", "000660", "373220"]


def _px_qv_range(
    start: str, end: str, codes: list[str] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """business-day 구간 종가/거래대금 매트릭스. codes[0]이 항상 최대 모멘텀."""
    cds = codes or _POOL_CODES
    idx = pd.DatetimeIndex(pd.bdate_range(start, end))
    px = pd.DataFrame(
        {c: [100.0 + i * (0.5 if c == cds[0] else 0.1) for i in range(len(idx))] for c in cds},
        index=idx,
    )
    qv = pd.DataFrame({c: [1_000_000.0] * len(idx) for c in cds}, index=idx)
    return px, qv


def _make_job_with_creds(tmp_path: Path, n_codes: int = 3) -> MomentumJob:
    pool_path = tmp_path / "pool_creds.csv"
    lines = ["code,name,tag"]
    lines += [f"{i:06d},종목{i},test" for i in range(n_codes)]
    pool_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    settings = Settings(
        telegram_bot_token="dummy",
        telegram_chat_id="123",
        kis_app_key="k",
        kis_app_secret="s",
        momentum_top_n=2,
        momentum_universe_size=10,
        momentum_pool_path=str(pool_path),
    )
    return MomentumJob(
        settings=settings,
        notifier=AsyncMock(),
        pool_path=pool_path,
        universe_state_path=tmp_path / "u.json",
        portfolio_state_path=tmp_path / "p.json",
    )


def _make_pool_csv(path: Path) -> None:
    path.write_text(
        "code,name,tag\n005930,삼성전자,core43\n000660,SK하이닉스,core43\n373220,LG에너지솔루션,core43\n",
        encoding="utf-8",
    )


def _make_px_qv(codes: list[str], n_bars: int = 300) -> tuple[pd.DataFrame, pd.DataFrame]:
    idx = pd.date_range("2024-01-01", periods=n_bars, freq="B")
    px = pd.DataFrame(
        {c: [100.0 + i * (0.5 if c == "005930" else 0.1) for i in range(n_bars)] for c in codes},
        index=idx,
    )
    qv = pd.DataFrame({c: [1_000_000.0] * n_bars for c in codes}, index=idx)
    return px, qv


@pytest.fixture
def job(tmp_path: Path) -> MomentumJob:
    pool_path = tmp_path / "pool.csv"
    _make_pool_csv(pool_path)
    settings = Settings(
        telegram_bot_token="dummy",
        telegram_chat_id="123",
        kis_app_key="",  # .env 실 크리덴셜 로드 차단 — 단위테스트가 실 KIS API를 건드리지 않도록
        kis_app_secret="",
        momentum_top_n=2,
        # 하한(ge=10). 실제 유니버스는 풀 3종이라 build_universe가 자연히 3개만 반환.
        momentum_universe_size=10,
        momentum_pool_path=str(pool_path),
    )
    notifier = AsyncMock()
    return MomentumJob(
        settings=settings,
        notifier=notifier,
        pool_path=pool_path,
        universe_state_path=tmp_path / "momentum_universe.json",
        portfolio_state_path=tmp_path / "momentum_portfolio.json",
    )


def _patch_matrix(job: MomentumJob, monkeypatch: pytest.MonkeyPatch) -> None:
    codes = ["005930", "000660", "373220"]
    px, qv = _make_px_qv(codes)
    monkeypatch.setattr(job, "load_matrix", lambda: (px, qv))


# ── 알림 포맷 스냅샷 ──────────────────────────────────────────────────────────


def test_format_alert_snapshot(job: MomentumJob) -> None:
    top = pd.DataFrame(
        {"code": ["005930", "000660"], "momentum": [0.234, 0.101], "close": [78000.0, 210000.0]}
    )
    text = job._format_alert(  # noqa: SLF001 — 포맷 순수 로직 직접 검증
        top,
        added=["005930"],
        removed=["373220"],
        asof=pd.Timestamp("2025-12-30"),
        name_map={"005930": "삼성전자", "000660": "SK하이닉스", "373220": "LG에너지솔루션"},
    )
    assert text == (
        "📊 M2 월간 리밸런스 (2025-12 마감)\n"
        "\n"
        "TOP10:\n"
        "1. 삼성전자(005930) — 12-1 모멘텀 +23.4% / 78,000\n"
        "2. SK하이닉스(000660) — 12-1 모멘텀 +10.1% / 210,000\n"
        "\n"
        "⬆ 편입: 삼성전자(005930)\n"
        "⬇ 편출: LG에너지솔루션(373220)\n"
        "\n"
        "다음 리밸런스: 2026-01 마지막 거래일\n"
        "\n"
        "⚠ 정보 제공용 알림입니다. 투자 판단·책임은 본인에게 있습니다."
    )


# ── run_once: dry_run vs 실전 ─────────────────────────────────────────────────


async def test_run_once_dry_run_does_not_notify_or_persist(
    job: MomentumJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_matrix(job, monkeypatch)
    result = await job.run_once(pd.Timestamp("2025-12-30"), dry_run=True)

    job._notifier.send_text.assert_not_awaited()  # type: ignore[attr-defined]  # noqa: SLF001
    assert not job._portfolio_state_path.exists()  # noqa: SLF001
    assert not job._universe_state_path.exists()  # noqa: SLF001
    assert len(result["top"]) == 2  # momentum_top_n=2


async def test_run_once_live_notifies_and_persists(
    job: MomentumJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_matrix(job, monkeypatch)
    await job.run_once(pd.Timestamp("2025-12-30"), dry_run=False)

    job._notifier.send_text.assert_awaited_once()  # type: ignore[attr-defined]  # noqa: SLF001
    assert job._portfolio_state_path.exists()  # noqa: SLF001
    saved = json.loads(job._portfolio_state_path.read_text(encoding="utf-8"))  # noqa: SLF001
    assert saved["asof"] == "2025-12-30"
    assert len(saved["codes"]) == 2


async def test_run_once_diff_against_previous_portfolio(
    job: MomentumJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_matrix(job, monkeypatch)
    job._save_portfolio(["373220", "000660"], pd.Timestamp("2025-11-28"))  # noqa: SLF001

    result = await job.run_once(pd.Timestamp("2025-12-30"), dry_run=False)
    # 373220은 삼성전자/SK하이닉스에 밀려 top2 밖 -> 편출, 005930은 신규 -> 편입
    assert "005930" in result["added"]
    assert "373220" in result["removed"]


# ── _maybe_rebalance: 페치 성공 게이트(P2-1) + 시도 상한(P2-2) — 마일스톤19-2 ──


async def test_maybe_rebalance_defers_on_fetch_failure(
    job: MomentumJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    """페치 실패 + 월말이 거래일(7/31) → 발화 안 함, 상태 미갱신 (P2-1 test 1)."""
    px, qv = _px_qv_range("2024-01-01", "2025-07-30")  # 7/31 미도착(페치 실패로 없음)
    monkeypatch.setattr(job, "load_matrix", lambda: (px, qv))
    job.fetch_pool = AsyncMock(return_value=False)  # type: ignore[method-assign]

    await job._maybe_rebalance(datetime(2025, 7, 31, 16, 30, tzinfo=_KST))  # noqa: SLF001

    job._notifier.send_text.assert_not_awaited()  # type: ignore[attr-defined]  # noqa: SLF001
    assert not job._portfolio_state_path.exists()  # noqa: SLF001
    assert job._last_rebalanced_asof is None  # noqa: SLF001


async def test_maybe_rebalance_catchup_fires_correct_asof_next_day(
    job: MomentumJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    """페치 실패 다음 날 성공 → 캐치업이 정확한 asof(7/31)로 1회 발화 (P2-1 test 2)."""
    px1, qv1 = _px_qv_range("2024-01-01", "2025-07-30")
    monkeypatch.setattr(job, "load_matrix", lambda: (px1, qv1))
    job.fetch_pool = AsyncMock(return_value=False)  # type: ignore[method-assign]
    await job._maybe_rebalance(datetime(2025, 7, 31, 16, 30, tzinfo=_KST))  # noqa: SLF001
    assert job._last_rebalanced_asof is None  # noqa: SLF001

    px2, qv2 = _px_qv_range("2024-01-01", "2025-07-31")  # 7/31 도착
    monkeypatch.setattr(job, "load_matrix", lambda: (px2, qv2))
    job.fetch_pool = AsyncMock(return_value=True)  # type: ignore[method-assign]
    await job._maybe_rebalance(datetime(2025, 8, 1, 16, 30, tzinfo=_KST))  # noqa: SLF001

    assert job._last_rebalanced_asof == date(2025, 7, 31)  # noqa: SLF001
    job._notifier.send_text.assert_awaited_once()  # type: ignore[attr-defined]  # noqa: SLF001


async def test_maybe_rebalance_holiday_fires_latest_on_success(
    job: MomentumJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    """페치 성공 + 오늘 캔들 없음(12/31 상시 휴장) → 12/30로 정상 발화 (P2-1 test 3 회귀)."""
    px, qv = _px_qv_range("2024-01-01", "2025-12-30")  # 12/31 휴장이라 없음
    monkeypatch.setattr(job, "load_matrix", lambda: (px, qv))
    job.fetch_pool = AsyncMock(return_value=True)  # type: ignore[method-assign]

    await job._maybe_rebalance(datetime(2025, 12, 31, 16, 30, tzinfo=_KST))  # noqa: SLF001

    assert job._last_rebalanced_asof == date(2025, 12, 30)  # noqa: SLF001
    job._notifier.send_text.assert_awaited_once()  # type: ignore[attr-defined]  # noqa: SLF001


async def test_maybe_rebalance_fetch_attempts_capped_per_day(
    job: MomentumJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    """실패 반복 시 fetch_pool 호출이 당일 상한에 걸린다 (P2-2 test 4)."""
    px, qv = _px_qv_range("2024-01-01", "2025-07-30")
    monkeypatch.setattr(job, "load_matrix", lambda: (px, qv))
    fetch_mock = AsyncMock(return_value=False)
    job.fetch_pool = fetch_mock  # type: ignore[method-assign]

    now = datetime(2025, 7, 31, 16, 30, tzinfo=_KST)
    for _ in range(_MAX_FETCH_ATTEMPTS_PER_DAY + 10):
        await job._maybe_rebalance(now)  # noqa: SLF001

    assert fetch_mock.await_count == _MAX_FETCH_ATTEMPTS_PER_DAY


async def test_maybe_rebalance_before_window_no_fetch(
    job: MomentumJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    """16:30 이전에는 페치조차 안 한다."""
    fetch_mock = AsyncMock(return_value=True)
    job.fetch_pool = fetch_mock  # type: ignore[method-assign]
    await job._maybe_rebalance(datetime(2025, 7, 31, 9, 0, tzinfo=_KST))  # noqa: SLF001
    fetch_mock.assert_not_awaited()


async def test_maybe_rebalance_already_done_no_fetch(
    job: MomentumJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    """이번 달을 이미 리밸런스했으면 후보 아님 → 페치 안 함 (중복 방지)."""
    job._save_portfolio(["005930", "000660"], pd.Timestamp("2025-07-31"))  # noqa: SLF001
    fetch_mock = AsyncMock(return_value=True)
    job.fetch_pool = fetch_mock  # type: ignore[method-assign]
    await job._maybe_rebalance(datetime(2025, 8, 1, 16, 30, tzinfo=_KST))  # noqa: SLF001
    fetch_mock.assert_not_awaited()


# ── fetch_pool bool 판정 ──────────────────────────────────────────────────────


async def test_fetch_pool_false_without_credentials(job: MomentumJob) -> None:
    """KIS 크리덴셜 미설정 → False (fixture job엔 KIS 키 없음)."""
    assert await job.fetch_pool() is False


async def test_fetch_pool_true_when_all_succeed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _make_job_with_creds(tmp_path, n_codes=5)
    monkeypatch.setattr("signal_program.cli._fetch_candles_kr_async", AsyncMock())
    assert await job.fetch_pool() is True


async def test_fetch_pool_false_on_systemic_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _make_job_with_creds(tmp_path, n_codes=5)

    async def _always_fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("KIS down")

    monkeypatch.setattr("signal_program.cli._fetch_candles_kr_async", _always_fail)
    assert await job.fetch_pool() is False


async def test_fetch_pool_tolerates_minor_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """소수 종목 실패(1/10 = 10% < 20% 임계치)는 True — 정상 운영 상폐/거래정지 허용."""
    job = _make_job_with_creds(tmp_path, n_codes=10)

    async def _fail_one(code: str, *args: object, **kwargs: object) -> None:
        if code == "000000":
            raise RuntimeError("delisted")

    monkeypatch.setattr("signal_program.cli._fetch_candles_kr_async", _fail_one)
    assert await job.fetch_pool() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
