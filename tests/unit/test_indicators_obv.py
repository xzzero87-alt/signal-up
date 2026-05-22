"""compute_obv — TDD RED → GREEN.

ADR-0010 AI 리스크 #1: obv_avg가 음수일 때 naive 공식 (x / obv_avg) 부호 반전 방지.
abs() 분모 적용으로 수정. 이 파일의 RED 테스트가 naive 구현을 걸러낸다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from signal_program.indicators.obv import compute_obv

KST = timezone(timedelta(hours=9))


def make_candles(
    closes: list[float],
    volumes: list[float] | None = None,
) -> pd.DataFrame:
    if volumes is None:
        volumes = [1.0] * len(closes)
    base = datetime(2026, 1, 1, tzinfo=KST)
    rows = [
        {
            "market": "KRW-BTC",
            "opened_at": base + timedelta(hours=i),
            "open": c,
            "high": c * 1.005,
            "low": c * 0.995,
            "close": c,
            "volume": v,
            "quote_volume": c * v,
        }
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]
    return pd.DataFrame(rows)


# ─── 핵심 RED 테스트: ADR-0010 AI 리스크 #1 ─────────────────────────────────


class TestOBVNegativeAverageSignReversal:
    """obv_avg < 0이고 obv < obv_avg (OBV 하락)일 때 buy_score가 양수가 되어선 안 된다.

    naive: (obv - obv_avg) / obv_avg = 음수 / 음수 = 양수 → 오류
    fix:   (obv - obv_avg) / abs(obv_avg) = 음수 / 양수 = 음수 → clip → 0
    """

    def _make_negative_avg_candles(self) -> pd.DataFrame:
        """5 소량 상승 + 20 대량 하락 → obv_avg < 0, obv << obv_avg."""
        up_closes = [100.0, 101.0, 102.0, 103.0, 104.0]
        up_volumes = [10.0] * 5
        down_closes = [104.0 - (i + 1) for i in range(20)]  # 103 → 84
        down_volumes = [100.0] * 20
        return make_candles(up_closes + down_closes, up_volumes + down_volumes)

    def test_buy_score_zero_when_obv_falling_and_avg_negative(self) -> None:
        """OBV 하락 + 음수 평균 → buy_score는 반드시 0.0이어야 한다."""
        result = compute_obv(self._make_negative_avg_candles(), lookback=20)
        buy_score = float(result["buy_score"].iloc[-1])
        assert buy_score == pytest.approx(0.0), (
            f"음수 평균 부호 반전 버그: buy_score={buy_score:.4f} (기대: 0.0)\n"
            "naive 공식은 약 0.94를 반환 — abs() 분모 미적용 의심"
        )

    def test_sell_score_positive_when_obv_falling_and_avg_negative(self) -> None:
        """OBV 하락 + 음수 평균 → sell_score는 양수여야 한다."""
        result = compute_obv(self._make_negative_avg_candles(), lookback=20)
        sell_score = float(result["sell_score"].iloc[-1])
        assert sell_score > 0.5, (
            f"음수 평균 시 sell_score 부호 반전: {sell_score:.4f} (기대: > 0.5)\n"
            "naive 공식은 약 -0.94 → clip → 0을 반환 — abs() 분모 미적용 의심"
        )

    def test_buy_and_sell_coherent_on_negative_avg(self) -> None:
        """음수 평균 시나리오에서 buy=0, sell>0 동시 성립."""
        result = compute_obv(self._make_negative_avg_candles(), lookback=20)
        last = result.iloc[-1]
        assert float(last["buy_score"]) == pytest.approx(0.0)
        assert float(last["sell_score"]) > 0.0


# ─── 범위 검증 ────────────────────────────────────────────────────────────────


class TestOBVScoreRange:
    """buy_score와 sell_score는 항상 [0, 1] 범위여야 한다."""

    def test_scores_bounded_uptrend(self) -> None:
        closes = [100.0 + i for i in range(40)]
        result = compute_obv(make_candles(closes), lookback=20)
        valid = result.dropna()
        assert (valid["buy_score"] >= 0.0).all()
        assert (valid["buy_score"] <= 1.0).all()
        assert (valid["sell_score"] >= 0.0).all()
        assert (valid["sell_score"] <= 1.0).all()

    def test_scores_bounded_downtrend(self) -> None:
        closes = [200.0 - i for i in range(40)]
        result = compute_obv(make_candles(closes), lookback=20)
        valid = result.dropna()
        assert (valid["buy_score"] >= 0.0).all()
        assert (valid["buy_score"] <= 1.0).all()
        assert (valid["sell_score"] >= 0.0).all()
        assert (valid["sell_score"] <= 1.0).all()

    def test_buy_sell_mutually_exclusive(self) -> None:
        """한 봉에서 buy_score > 0이면 sell_score = 0이어야 한다 (clipping 특성)."""
        closes = [100.0 + i for i in range(40)]
        result = compute_obv(make_candles(closes), lookback=20)
        valid = result.dropna()
        both_positive = (valid["buy_score"] > 0) & (valid["sell_score"] > 0)
        assert not both_positive.any(), "buy_score와 sell_score가 동시에 양수인 행 발견"


# ─── NaN 행 검증 ──────────────────────────────────────────────────────────────


class TestOBVNaNRows:
    """첫 (lookback-1)개 행은 buy_score/sell_score가 NaN이어야 한다."""

    def test_nan_prefix_default_lookback(self) -> None:
        lookback = 20
        closes = [100.0 + i for i in range(lookback + 5)]
        result = compute_obv(make_candles(closes), lookback=lookback)
        assert result["obv"].isna().sum() == 0, "obv raw 값에는 NaN이 없어야 함"
        assert result["buy_score"].isna().sum() == lookback - 1
        assert result["sell_score"].isna().sum() == lookback - 1

    def test_nan_prefix_custom_lookback(self) -> None:
        lookback = 5
        closes = [100.0 + i for i in range(lookback + 3)]
        result = compute_obv(make_candles(closes), lookback=lookback)
        assert result["buy_score"].isna().sum() == lookback - 1


# ─── OBV raw 누적 값 검증 ─────────────────────────────────────────────────────


class TestOBVRawAccumulation:
    def test_first_candle_is_zero(self) -> None:
        """첫 봉은 이전 가격 없음 → OBV = 0."""
        closes = [100.0, 101.0, 102.0]
        result = compute_obv(make_candles(closes, [50.0, 50.0, 50.0]))
        assert float(result["obv"].iloc[0]) == pytest.approx(0.0)

    def test_obv_accumulates_on_up_moves(self) -> None:
        """모든 봉이 상승 → OBV = sum(volume[1:])."""
        closes = [100.0 + i for i in range(6)]
        volumes = [50.0] * 6
        result = compute_obv(make_candles(closes, volumes))
        assert float(result["obv"].iloc[-1]) == pytest.approx(5 * 50.0)

    def test_obv_accumulates_on_down_moves(self) -> None:
        """모든 봉이 하락 → OBV = -sum(volume[1:])."""
        closes = [110.0 - i for i in range(6)]
        volumes = [50.0] * 6
        result = compute_obv(make_candles(closes, volumes))
        assert float(result["obv"].iloc[-1]) == pytest.approx(-5 * 50.0)

    def test_flat_price_no_obv_change(self) -> None:
        """가격 동일 → OBV = 0 유지."""
        closes = [100.0] * 10
        result = compute_obv(make_candles(closes, [50.0] * 10))
        assert np.allclose(result["obv"].to_numpy(), 0.0)
