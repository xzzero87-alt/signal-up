"""momentum/core.py 순수 함수 테스트 (ADR-0031)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from signal_program.momentum.core import (
    build_universe,
    diff_portfolio,
    pending_rebalance_asof,
    select_top10,
)

# ── build_universe ──────────────────────────────────────────────────────────


def _make_dec_qv(values: dict[str, list[float]], days: int = 20) -> pd.DataFrame:
    """2021-12 거래일 `days`일치 거래대금 DataFrame. values의 각 리스트 길이는 <= days.

    리스트가 days보다 짧으면 앞쪽 결측(NaN)으로 채워 "거래일 부족" 종목을 표현한다.
    """
    idx = pd.date_range("2021-12-01", periods=days, freq="B")  # 영업일만
    data = {}
    for code, vals in values.items():
        padded = [None] * (days - len(vals)) + list(vals)
        data[code] = padded
    return pd.DataFrame(data, index=idx)


def test_build_universe_top_n_selection() -> None:
    qv = _make_dec_qv(
        {
            "A": [100.0] * 20,
            "B": [50.0] * 20,
            "C": [200.0] * 20,
        }
    )
    uni = build_universe(qv, year=2022, top_n=2)
    assert uni == ["C", "A"]


def test_build_universe_excludes_thin_trading() -> None:
    """당월 거래일 10일 미만(신규상장 등)인 종목은 평균값이 아무리 커도 제외."""
    qv = _make_dec_qv(
        {
            "THICK": [10.0] * 20,
            "THIN": [999.0] * 5,  # 5일치뿐 -> 10일 미만, 제외 대상
        }
    )
    uni = build_universe(qv, year=2022, top_n=10)
    assert uni == ["THICK"]
    assert "THIN" not in uni


def test_build_universe_uses_prior_year_december() -> None:
    """round2_m2_backtest.build_universes()와 동일하게, 대상 연월 데이터가 아예
    없으면 KeyError(방어적 fallback 없음 — 레퍼런스 로직과 동일 동작 유지)."""
    qv = _make_dec_qv({"A": [100.0] * 20})
    with pytest.raises(KeyError):
        build_universe(qv, year=2023, top_n=10)  # 2022-12 데이터 없음


# ── select_top10 ─────────────────────────────────────────────────────────────


def _make_px(codes: list[str], n_bars: int = 300, base: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n_bars, freq="B")
    data = {c: [base] * n_bars for c in codes}
    return pd.DataFrame(data, index=idx)


def test_select_top10_ranks_by_momentum() -> None:
    px = _make_px(["A", "B", "C"], n_bars=300)
    # A: 최근 상승, B: 최근 하락, C: 변화 없음
    px.loc[px.index[-260:], "A"] = [100.0 + i for i in range(260)]  # 우상향
    px.loc[px.index[-260:], "B"] = [100.0 - i * 0.1 for i in range(260)]  # 우하향
    asof = px.index[-1]
    top = select_top10(px, universe=["A", "B", "C"], asof=asof, n=2)
    assert list(top["code"]) == ["A", "C"]
    assert top.iloc[0]["momentum"] > top.iloc[1]["momentum"]
    assert set(top.columns) == {"code", "momentum", "close"}


def test_select_top10_insufficient_history_returns_empty() -> None:
    px = _make_px(["A", "B"], n_bars=100)  # lb_long=252 미달
    asof = px.index[-1]
    top = select_top10(px, universe=["A", "B"], asof=asof)
    assert top.empty
    assert list(top.columns) == ["code", "momentum", "close"]


def test_select_top10_universe_smaller_than_n() -> None:
    px = _make_px(["A", "B"], n_bars=300)
    asof = px.index[-1]
    top = select_top10(px, universe=["A", "B"], asof=asof, n=10)
    assert len(top) == 2  # n=10이어도 유니버스가 2개면 2개만


def test_select_top10_excludes_history_missing_codes() -> None:
    """유니버스에 있지만 px 컬럼 자체에 없는 종목은 자연 제외."""
    px = _make_px(["A"], n_bars=300)
    asof = px.index[-1]
    top = select_top10(px, universe=["A", "GHOST"], asof=asof, n=5)
    assert list(top["code"]) == ["A"]


# ── diff_portfolio ───────────────────────────────────────────────────────────


def test_diff_portfolio_added_and_removed() -> None:
    added, removed = diff_portfolio(prev=["A", "B", "C"], curr=["B", "C", "D"])
    assert added == ["D"]
    assert removed == ["A"]


def test_diff_portfolio_no_change() -> None:
    added, removed = diff_portfolio(prev=["A", "B"], curr=["B", "A"])
    assert added == []
    assert removed == []


def test_diff_portfolio_full_turnover() -> None:
    added, removed = diff_portfolio(prev=["A", "B"], curr=["C", "D"])
    assert added == ["C", "D"]
    assert removed == ["A", "B"]


# ── pending_rebalance_asof ───────────────────────────────────────────────────
# is_last_trading_day_of_month의 발화 스케줄 결함(마일스톤19 Evaluator 발견) 수정 후
# 재작성된 테스트. 라이브 조건(candle_dates가 today까지만 관측됨)을 그대로 모사한다.


def test_pending_rebalance_asof_mid_month_already_handled_is_none() -> None:
    """월중(당월 미종료) + 직전 완료월(10월)은 이미 처리됨 -> None."""
    dates = pd.DatetimeIndex(pd.bdate_range("2025-11-01", "2025-11-17"))
    result = pending_rebalance_asof(
        dates, today=date(2025, 11, 17), last_rebalanced_asof=date(2025, 10, 31)
    )
    assert result is None


def test_pending_rebalance_asof_month_end_weekday_fires() -> None:
    """9월 마지막 캘린더일(9/30, 평일)에 체크 -> 9월 asof로 발화."""
    dates = pd.DatetimeIndex(pd.bdate_range("2025-09-01", "2025-09-30"))
    result = pending_rebalance_asof(
        dates, today=date(2025, 9, 30), last_rebalanced_asof=date(2025, 8, 29)
    )
    assert result == pd.Timestamp("2025-09-30")


def test_pending_rebalance_asof_december_holiday_regression() -> None:
    """KRX 12/31 상시 휴장 회귀 — 라이브에서 12/31 저녁 체크해도 asof=12/30로 확정.

    구버전(is_last_trading_day_of_month)은 이 시나리오에서 12월 내내 False만
    반환해 12월 리밸런스가 통째로 누락됐다(마일스톤19 Evaluator 발견).
    """
    dates = pd.DatetimeIndex(pd.bdate_range("2025-12-01", "2025-12-30"))  # 12/31 휴장, 미관측
    result = pending_rebalance_asof(
        dates, today=date(2025, 12, 31), last_rebalanced_asof=date(2025, 11, 28)
    )
    assert result == pd.Timestamp("2025-12-30")


def test_pending_rebalance_asof_month_end_weekend_regression() -> None:
    """2025-08-31(일)은 원천적으로 비거래일 -> 8/29(금)이 asof로 확정."""
    dates = pd.DatetimeIndex(pd.bdate_range("2025-08-01", "2025-08-29"))
    result = pending_rebalance_asof(
        dates, today=date(2025, 8, 31), last_rebalanced_asof=date(2025, 7, 31)
    )
    assert result == pd.Timestamp("2025-08-29")


def test_pending_rebalance_asof_catchup_after_missed_trigger_day() -> None:
    """11월 트리거일(11/28)을 건너뛰고 12/1에 체크해도 11월 asof로 캐치업 발화."""
    dates = pd.DatetimeIndex(pd.bdate_range("2025-11-01", "2025-12-01"))
    result = pending_rebalance_asof(
        dates, today=date(2025, 12, 1), last_rebalanced_asof=date(2025, 10, 31)
    )
    assert result == pd.Timestamp("2025-11-28")


def test_pending_rebalance_asof_no_duplicate_after_already_fired() -> None:
    """같은 달에 이미 리밸런스했으면(11월 asof 기록됨) 재확인해도 None."""
    dates = pd.DatetimeIndex(pd.bdate_range("2025-11-01", "2025-12-01"))
    result = pending_rebalance_asof(
        dates, today=date(2025, 12, 1), last_rebalanced_asof=date(2025, 11, 28)
    )
    assert result is None


def test_pending_rebalance_asof_first_run_no_prior_state() -> None:
    """last_rebalanced_asof가 없으면(최초 실행) 당월 종료 시 바로 발화."""
    dates = pd.DatetimeIndex(pd.bdate_range("2025-09-01", "2025-09-30"))
    result = pending_rebalance_asof(dates, today=date(2025, 9, 30), last_rebalanced_asof=None)
    assert result == pd.Timestamp("2025-09-30")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
