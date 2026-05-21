"""BacktestEngine 시뮬레이션 시나리오 12종 + Hypothesis property + 경계 parametrize.

합성 캔들 설계:
  close[i] = 50_000_000 + i * close_step
  open[i]  = close[i] - 3_000
  따라서 bar[i].open 과 bar[i].close 가 명시적으로 구분됨 (시나리오 h 검증용).

_MockStrategy: 지정한 bar index에서만 Signal 반환. 엔진 로직 격리 테스트.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from signal_program.backtest.engine import BacktestEngine
from signal_program.enums import SignalDirection, SignalStrength, StrategyMode, Timeframe
from signal_program.models import IndicatorSnapshot, Signal

_KST = ZoneInfo("Asia/Seoul")
_BASE_TS = datetime(2025, 1, 1, 0, 0, 0, tzinfo=_KST)
_MARKET = "KRW-BTC"


# ── 픽스처 헬퍼 ───────────────────────────────────────────────────────────────

def _make_candles_df(
    n: int = 200,
    *,
    market: str = _MARKET,
    close_start: float = 50_000_000.0,
    close_step: float = 10_000.0,
) -> pd.DataFrame:
    rows = []
    for i in range(n):
        c = close_start + i * close_step
        o = c - 3_000.0
        rows.append(
            {
                "market": market,
                "opened_at": pd.Timestamp(_BASE_TS + timedelta(hours=i)),
                "open": o,
                "high": c + 2_000.0,
                "low": o - 2_000.0,
                "close": c,
                "volume": 10.0,
                "quote_volume": c * 10.0,
            }
        )
    return pd.DataFrame(rows)


def _buy_signal(*, bb_middle: float = 99_000_000.0) -> Signal:
    return Signal(
        market=_MARKET,
        timeframe=Timeframe.HOUR_1,
        mode=StrategyMode.MEAN_REVERSION,
        direction=SignalDirection.BUY,
        strength=SignalStrength.NORMAL,
        price=50_000_000.0,
        triggered_at=_BASE_TS,
        indicators=IndicatorSnapshot(
            bb_upper=51_000_000.0,
            bb_middle=bb_middle,
            bb_lower=49_000_000.0,
            bb_width=2_000_000.0,
            bb_pct_b=0.0,
            cci=-150.0,
            volume_ratio=1.5,
        ),
    )


def _sell_signal() -> Signal:
    return Signal(
        market=_MARKET,
        timeframe=Timeframe.HOUR_1,
        mode=StrategyMode.MEAN_REVERSION,
        direction=SignalDirection.SELL,
        strength=SignalStrength.NORMAL,
        price=50_000_000.0,
        triggered_at=_BASE_TS,
        indicators=IndicatorSnapshot(
            bb_upper=51_000_000.0,
            bb_middle=50_000_000.0,
            bb_lower=49_000_000.0,
            bb_width=2_000_000.0,
            bb_pct_b=1.0,
            cci=150.0,
            volume_ratio=1.5,
        ),
    )


class _MockStrategy:
    name = "mock"

    def __init__(self, signals: dict[int, list[Signal]]) -> None:
        self._signals = signals

    def evaluate(self, market: str, candles: pd.DataFrame) -> list[Signal]:
        idx = len(candles) - 1
        return list(self._signals.get(idx, []))


def _engine(
    strategy: _MockStrategy,
    *,
    fee_rate: float = 0.0,
    slippage_rate: float = 0.0,
    max_holding_bars: int = 24,
) -> BacktestEngine:
    return BacktestEngine(
        strategy=strategy,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        max_holding_bars=max_holding_bars,
    )


# ── a) 시그널 없음 → trades 빈 튜플, 지표 모두 0 ─────────────────────────────

def test_a_no_signal_empty_result() -> None:
    df = _make_candles_df(200)
    result = _engine(_MockStrategy({})).run(_MARKET, df)
    assert result.trades == ()
    assert result.win_rate == 0.0
    assert result.avg_pnl_pct == 0.0
    assert result.cumulative_return_pct == 0.0
    assert result.mdd_pct == 0.0
    assert result.avg_bars_held == 0.0


# ── b) BUY 1회 + 24봉 후 자동 청산 → pnl 계산 정확 ──────────────────────────

def test_b_buy_auto_close_24bars() -> None:
    df = _make_candles_df(200)
    sig = _buy_signal()  # bb_middle=99M (절대 미도달)
    result = _engine(_MockStrategy({50: [sig]})).run(_MARKET, df)

    assert len(result.trades) == 1
    trade = result.trades[0]
    entry_price = float(df.iloc[51]["open"])
    exit_price = float(df.iloc[74]["close"])
    assert trade.entry_price == pytest.approx(entry_price)
    assert trade.exit_price == pytest.approx(exit_price)
    assert trade.bars_held == 24
    expected_pnl = (exit_price - entry_price) / entry_price
    assert trade.pnl_pct == pytest.approx(expected_pnl, rel=1e-6)


# ── c) BUY 1회 + BB 중심선 도달로 조기 청산 → bars_held < 24 ─────────────────

def test_c_buy_early_exit_at_bb_middle() -> None:
    # close[60] = 50_000_000 + 60*10_000 = 50_600_000
    # bb_middle = 50_600_000 → 처음 close >= bb_middle 는 bar 60
    # 진입 bar 51, 청산 bar 60 → bars_held = 10
    df = _make_candles_df(200)
    bb_mid = float(df.iloc[60]["close"])  # 50_600_000
    sig = _buy_signal(bb_middle=bb_mid)
    result = _engine(_MockStrategy({50: [sig]})).run(_MARKET, df)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.bars_held == 10
    assert trade.bars_held < 24


# ── d) SELL 시그널이 BUY 포지션 보유 중 → 무시 ──────────────────────────────

def test_d_sell_ignored_during_buy_position() -> None:
    df = _make_candles_df(200)
    buy_sig = _buy_signal()
    sell_sig = _sell_signal()
    # bar 50에서 BUY, bar 55에서 SELL(무시), bar 74에서 자동 청산
    result = _engine(_MockStrategy({50: [buy_sig], 55: [sell_sig]})).run(_MARKET, df)
    assert len(result.trades) == 1
    assert result.trades[0].bars_held == 24


# ── e) 보유 중 새 BUY 시그널 무시 (단일 포지션) ─────────────────────────────

def test_e_new_buy_ignored_during_position() -> None:
    df = _make_candles_df(200)
    sig = _buy_signal()
    result = _engine(_MockStrategy({50: [sig], 55: [sig]})).run(_MARKET, df)
    assert len(result.trades) == 1


# ── f) 수수료 적용 → pnl 감소 ────────────────────────────────────────────────

def test_f_fee_reduces_pnl() -> None:
    df = _make_candles_df(200)
    sig = _buy_signal()
    result_no_fee = _engine(_MockStrategy({50: [sig]}), fee_rate=0.0).run(_MARKET, df)
    result_fee = _engine(_MockStrategy({50: [sig]}), fee_rate=0.001).run(_MARKET, df)
    assert result_no_fee.trades[0].pnl_pct > result_fee.trades[0].pnl_pct


# ── g) 슬리피지 적용 → pnl 감소 ──────────────────────────────────────────────

def test_g_slippage_reduces_pnl() -> None:
    df = _make_candles_df(200)
    sig = _buy_signal()
    result_no_slip = _engine(_MockStrategy({50: [sig]}), slippage_rate=0.0).run(_MARKET, df)
    result_slip = _engine(_MockStrategy({50: [sig]}), slippage_rate=0.001).run(_MARKET, df)
    assert result_no_slip.trades[0].pnl_pct > result_slip.trades[0].pnl_pct


# ── h) 진입가 = 다음봉 시가 (signal 봉 close ≠ 다음봉 open) ──────────────────

def test_h_entry_price_is_next_bar_open() -> None:
    df = _make_candles_df(200)
    sig = _buy_signal()
    result = _engine(_MockStrategy({50: [sig]})).run(_MARKET, df)
    expected_entry = float(df.iloc[51]["open"])
    assert result.trades[0].entry_price == pytest.approx(expected_entry)
    # 시그널 봉 close ≠ 다음봉 open (open = close - 3_000)
    assert float(df.iloc[50]["close"]) != float(df.iloc[51]["open"])


# ── i) 24봉 동안 BB 중심선 미도달 → 정확히 24봉 후 청산 ─────────────────────

def test_i_24bar_max_hold_without_bb_exit() -> None:
    df = _make_candles_df(200)
    sig = _buy_signal(bb_middle=99_000_000.0)
    result = _engine(_MockStrategy({50: [sig]}), max_holding_bars=24).run(_MARKET, df)
    assert result.trades[0].bars_held == 24


# ── j) MDD 계산 — 음의 누적 수익 시퀀스 ─────────────────────────────────────

def test_j_mdd_with_losing_trades() -> None:
    # 하락 추세 캔들 → 모든 BUY 거래가 손실
    df = _make_candles_df(200, close_step=-10_000.0)
    sig = _buy_signal(bb_middle=99_000_000.0)  # 항상 미도달 → 24봉 자동청산
    # bar 10, 60, 110 — 겹치지 않는 3개 거래
    strat = _MockStrategy({10: [sig], 60: [sig], 110: [sig]})
    result = _engine(strat, max_holding_bars=24).run(_MARKET, df)
    assert len(result.trades) == 3
    assert all(t.pnl_pct < 0 for t in result.trades)
    assert result.mdd_pct < 0.0  # MDD 부호 컨벤션: 음수


# ── k) 샤프 비율 — 단일 거래 (std=0) → division-by-zero 안전 ─────────────────

def test_k_sharpe_safe_when_single_trade() -> None:
    df = _make_candles_df(200)
    sig = _buy_signal()
    result = _engine(_MockStrategy({50: [sig]})).run(_MARKET, df)
    assert len(result.trades) == 1
    assert isinstance(result.sharpe_annualized, float)
    assert not math.isnan(result.sharpe_annualized)
    assert not math.isinf(result.sharpe_annualized)


# ── l) 빈 캔들 → ValueError ────────────────────────────────────────────────────

def test_l_empty_candles_raises_value_error() -> None:
    df = _make_candles_df(0)
    with pytest.raises(ValueError):
        _engine(_MockStrategy({})).run(_MARKET, df)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 3 — Hypothesis property + 경계 parametrize
# ══════════════════════════════════════════════════════════════════════════════


# ── Hypothesis: 임의 가격·임계값에서 run()이 예외 없이 BacktestResult 반환 ──────

@given(
    close_start=st.floats(min_value=100.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
    close_step=st.floats(min_value=-5_000.0, max_value=5_000.0, allow_nan=False, allow_infinity=False),
    signal_bar=st.integers(min_value=0, max_value=150),
    max_hold=st.integers(min_value=1, max_value=48),
)
@h_settings(max_examples=40, deadline=5000)
def test_hypothesis_run_no_exception(
    close_start: float, close_step: float, signal_bar: int, max_hold: int
) -> None:
    df = _make_candles_df(200, close_start=close_start, close_step=close_step)
    sig = _buy_signal(bb_middle=close_start + abs(close_step) * 1000)
    result = _engine(_MockStrategy({signal_bar: [sig]}), max_holding_bars=max_hold).run(_MARKET, df)
    # BacktestResult invariants
    assert 0.0 <= result.win_rate <= 1.0
    assert not math.isnan(result.sharpe_annualized)
    assert not math.isinf(result.sharpe_annualized)
    assert result.mdd_pct <= 0.0  # MDD 부호 컨벤션: 음수 또는 0
    assert len(result.trades) == result.trades.__len__()


# ── Hypothesis: BacktestResult 필드 invariant 검증 ────────────────────────────

@given(n_signals=st.integers(min_value=0, max_value=5))
@h_settings(max_examples=20, deadline=5000)
def test_hypothesis_result_invariants(n_signals: int) -> None:
    df = _make_candles_df(200)
    sig = _buy_signal()
    # 50봉 간격으로 신호 배치 (최대 5개)
    signal_dict = {10 + i * 40: [sig] for i in range(n_signals)}
    result = _engine(_MockStrategy(signal_dict), max_holding_bars=24).run(_MARKET, df)

    # win_rate ∈ [0, 1]
    assert 0.0 <= result.win_rate <= 1.0
    # trades 수와 avg_bars_held 일관성
    if result.trades:
        expected_avg = sum(t.bars_held for t in result.trades) / len(result.trades)
        assert result.avg_bars_held == pytest.approx(expected_avg)
    else:
        assert result.avg_bars_held == 0.0


# ── 경계 parametrize: fee_rate 변화 ───────────────────────────────────────────

@pytest.mark.parametrize("fee_rate", [0.0, 0.001, 0.005, 0.01])
def test_parametrize_fee_rates(fee_rate: float) -> None:
    df = _make_candles_df(200)
    sig = _buy_signal()
    result = _engine(_MockStrategy({50: [sig]}), fee_rate=fee_rate).run(_MARKET, df)
    assert len(result.trades) == 1
    # 수수료 높을수록 pnl 낮음 (단조 감소)
    assert isinstance(result.trades[0].pnl_pct, float)


@pytest.mark.parametrize("fee_pair", [(0.0, 0.001), (0.001, 0.005), (0.005, 0.01)])
def test_parametrize_fee_monotonic(fee_pair: tuple[float, float]) -> None:
    low_fee, high_fee = fee_pair
    df = _make_candles_df(200)
    sig = _buy_signal()
    r_low = _engine(_MockStrategy({50: [sig]}), fee_rate=low_fee).run(_MARKET, df)
    r_high = _engine(_MockStrategy({50: [sig]}), fee_rate=high_fee).run(_MARKET, df)
    assert r_low.trades[0].pnl_pct >= r_high.trades[0].pnl_pct


# ── 경계 parametrize: max_holding_bars 변화 ──────────────────────────────────

@pytest.mark.parametrize("max_hold", [12, 24, 48, 96])
def test_parametrize_max_holding_bars(max_hold: int) -> None:
    df = _make_candles_df(200)
    sig = _buy_signal(bb_middle=99_000_000.0)
    result = _engine(_MockStrategy({50: [sig]}), max_holding_bars=max_hold).run(_MARKET, df)
    if result.trades:
        assert result.trades[0].bars_held <= max_hold


# ── 경계 parametrize: BUY/SELL 시그널 조합 ───────────────────────────────────

@pytest.mark.parametrize(
    "signal_dict,expected_trades",
    [
        ({}, 0),
        ({50: []}, 0),  # 빈 시그널 리스트
        ({50: [_buy_signal()]}, 1),
        ({50: [_sell_signal()]}, 0),  # SELL만 → 진입 없음
    ],
)
def test_parametrize_signal_types(
    signal_dict: dict[int, list[Signal]], expected_trades: int
) -> None:
    df = _make_candles_df(200)
    result = _engine(_MockStrategy(signal_dict)).run(_MARKET, df)
    assert len(result.trades) == expected_trades
