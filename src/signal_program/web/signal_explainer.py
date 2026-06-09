"""전략별 시그널 해석 텍스트 생성 — 순수 함수, 부작용 없음 (P2 v2.3).

explain()은 신호 레코드 dict와 미리 계산된 confidence 정수를 받아
사람이 읽을 수 있는 SignalExplanation을 반환한다.

각 전략 모드(A~F)의 pass/warn 판단 기준은 실제 전략 코드의 임계값을 따른다:
  A (MEAN_REVERSION): %B ≤ 0 (매수) / ≥ 1 (매도), cci ≤ -100 / ≥ 100, vol ≥ 1.0
  B (SQUEEZE_BREAKOUT): %B ≥ 1 (매수) / ≤ 0 (매도), cci > 100 / < -100, vol ≥ 1.5
  C (WEIGHTED_SCORE): score ≥ 0.65
  D (FRACTAL_BREAKOUT): vol ≥ 1.2, age ≤ 20
  E (DONCHIAN_BREAKOUT): vol ≥ 1.5 (강도 기준)
  F (RSI2_REVERSION): rsi2 < 10 (매수) / > 90 (매도)
"""

from __future__ import annotations

from typing import Any, Literal

from signal_program.web.schemas import SignalExplanation, SignalExplanationReason

_ADVISORY = "자동매매가 아닌 참고용 시그널입니다."
_Status = Literal["pass", "warn", "neutral"]


def _r(label: str, value: str, status: _Status) -> SignalExplanationReason:
    return SignalExplanationReason(label=label, value=value, status=status)


def _fmt(v: Any, d: int = 2) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{d}f}"
    except (TypeError, ValueError):
        return "—"


def _vol(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.2f}×"
    except (TypeError, ValueError):
        return "—"


def explain(
    signal_id: str,
    sig: dict[str, Any],
    indicators: dict[str, Any],
    confidence: int,
) -> SignalExplanation:
    """신호 레코드에서 사람이 읽을 수 있는 해석을 생성한다."""
    mode = str(sig.get("mode", "A"))
    direction = str(sig.get("direction", "buy"))

    _dispatch = {
        "A": _mean_reversion,
        "B": _squeeze_breakout,
        "C": _weighted_score,
        "D": _fractal_breakout,
        "E": _donchian_breakout,
        "F": _rsi2_reversion,
    }
    handler = _dispatch.get(mode, _unknown)
    return handler(signal_id, direction, indicators, confidence)


# ── 전략별 해석 함수 ──────────────────────────────────────────────────────────


def _mean_reversion(
    signal_id: str, direction: str, ind: dict[str, Any], confidence: int
) -> SignalExplanation:
    bb = ind.get("bb_pct_b")
    cci = ind.get("cci")
    vol = ind.get("volume_ratio")

    if direction == "buy":
        summary = "BB 하단 이탈과 CCI 과매도가 확인된 평균회귀 매수 신호입니다."
        bb_ok: bool = bb is not None and float(bb) <= 0.0
        cci_ok: bool = cci is not None and float(cci) <= -100
    else:
        summary = "BB 상단 돌파와 CCI 과매수가 확인된 평균회귀 매도 신호입니다."
        bb_ok = bb is not None and float(bb) >= 1.0
        cci_ok = cci is not None and float(cci) >= 100

    vol_ok: bool = vol is not None and float(vol) >= 1.0
    reasons = [
        _r("BB %B", _fmt(bb), "pass" if bb_ok else "warn"),
        _r("CCI (≤-100 또는 ≥100)", _fmt(cci, 1), "pass" if cci_ok else "warn"),
        _r("거래량 비율 (≥1.0×)", _vol(vol), "pass" if vol_ok else "warn"),
    ]
    return SignalExplanation(
        signal_id=signal_id,
        confidence=confidence,
        summary=summary,
        reasons=reasons,
        warnings=[
            "평균회귀 신호는 강한 추세 구간에서 실패할 수 있습니다.",
            _ADVISORY,
        ],
    )


def _squeeze_breakout(
    signal_id: str, direction: str, ind: dict[str, Any], confidence: int
) -> SignalExplanation:
    bb = ind.get("bb_pct_b")
    cci = ind.get("cci")
    vol = ind.get("volume_ratio")

    if direction == "buy":
        summary = "볼린저 스퀴즈 후 상단 돌파·CCI 과매수가 확인된 돌파 매수 신호입니다."
        bb_ok: bool = bb is not None and float(bb) >= 1.0
        cci_ok: bool = cci is not None and float(cci) > 100
    else:
        summary = "볼린저 스퀴즈 후 하단 이탈·CCI 과매도가 확인된 돌파 매도 신호입니다."
        bb_ok = bb is not None and float(bb) <= 0.0
        cci_ok = cci is not None and float(cci) < -100

    vol_ok: bool = vol is not None and float(vol) >= 1.5
    reasons = [
        _r("BB %B", _fmt(bb), "pass" if bb_ok else "warn"),
        _r("CCI (>100 또는 <-100)", _fmt(cci, 1), "pass" if cci_ok else "warn"),
        _r("거래량 비율 (≥1.5×)", _vol(vol), "pass" if vol_ok else "warn"),
    ]
    return SignalExplanation(
        signal_id=signal_id,
        confidence=confidence,
        summary=summary,
        reasons=reasons,
        warnings=[
            "스퀴즈 돌파 신호는 가짜 돌파(fakeout)가 발생할 수 있습니다.",
            _ADVISORY,
        ],
    )


def _weighted_score(
    signal_id: str, direction: str, ind: dict[str, Any], confidence: int
) -> SignalExplanation:
    bb = ind.get("bb_pct_b")
    cci = ind.get("cci")
    vol = ind.get("volume_ratio")
    score = ind.get("weighted_score") or ind.get("score")

    action = "매수" if direction == "buy" else "매도"
    summary = f"4지표 가중치 합산 점수가 임계값(0.65)을 초과한 {action} 신호입니다."
    score_ok: bool = score is not None and float(score) >= 0.65

    reasons = [
        _r("BB 기여", _fmt(bb), "neutral"),
        _r("CCI 기여", _fmt(cci, 1), "neutral"),
        _r("거래량 비율", _vol(vol), "neutral"),
        _r(
            "종합 점수 (≥0.65)",
            _fmt(score) if score is not None else "—",
            "pass" if score_ok else "warn",
        ),
    ]
    return SignalExplanation(
        signal_id=signal_id,
        confidence=confidence,
        summary=summary,
        reasons=reasons,
        warnings=[
            "4지표 가중치 모델은 지표 간 상관관계가 높을 때 과신호가 발생할 수 있습니다.",
            _ADVISORY,
        ],
    )


def _fractal_breakout(
    signal_id: str, direction: str, ind: dict[str, Any], confidence: int
) -> SignalExplanation:
    vol = ind.get("volume_ratio")
    fractal_level = (
        ind.get("fractal_level") or ind.get("up_fractal_level") or ind.get("down_fractal_level")
    )
    fractal_age = ind.get("fractal_age") or ind.get("up_age") or ind.get("down_age")

    action = "상단 프랙탈 돌파 매수" if direction == "buy" else "하단 프랙탈 이탈 매도"
    summary = f"Williams Fractal {action} 신호입니다."
    vol_ok: bool = vol is not None and float(vol) >= 1.2
    age_ok: bool = fractal_age is not None and int(fractal_age) <= 20

    reasons = [
        _r("프랙탈 레벨", _fmt(fractal_level, 0), "neutral"),
        _r(
            "프랙탈 나이 (≤20봉)",
            str(int(fractal_age)) if fractal_age is not None else "—",
            "pass" if age_ok else "warn",
        ),
        _r("거래량 비율 (≥1.2×)", _vol(vol), "pass" if vol_ok else "warn"),
    ]
    return SignalExplanation(
        signal_id=signal_id,
        confidence=confidence,
        summary=summary,
        reasons=reasons,
        warnings=[
            "프랙탈 돌파 신호는 횡보 구간에서 거짓 신호가 발생할 수 있습니다.",
            _ADVISORY,
        ],
    )


def _donchian_breakout(
    signal_id: str, direction: str, ind: dict[str, Any], confidence: int
) -> SignalExplanation:
    vol = ind.get("volume_ratio")
    dc_level = ind.get("dc_upper") if direction == "buy" else ind.get("dc_lower")

    action = "20봉 최고가 돌파 매수" if direction == "buy" else "10봉 최저가 이탈 매도"
    summary = f"Donchian 채널 {action} 신호입니다."
    vol_strong: bool = vol is not None and float(vol) >= 1.5

    reasons = [
        _r("Donchian 기준가", _fmt(dc_level, 0), "neutral"),
        _r("거래량 비율 (강도 기준 ≥1.5×)", _vol(vol), "pass" if vol_strong else "neutral"),
    ]
    return SignalExplanation(
        signal_id=signal_id,
        confidence=confidence,
        summary=summary,
        reasons=reasons,
        warnings=[
            "Donchian 추세추종 전략은 횡보장에서 손실이 누적될 수 있습니다.",
            _ADVISORY,
        ],
    )


def _rsi2_reversion(
    signal_id: str, direction: str, ind: dict[str, Any], confidence: int
) -> SignalExplanation:
    rsi2 = ind.get("rsi2")
    trend_sma = ind.get("trend_sma") or ind.get("sma_200")
    vol = ind.get("volume_ratio")

    if direction == "buy":
        summary = "200봉 이동평균 위에서 RSI(2) 과매도 확인된 평균회귀 매수 신호입니다."
        rsi_ok: bool = rsi2 is not None and float(rsi2) < 10
    else:
        summary = "200봉 이동평균 아래에서 RSI(2) 과매수 확인된 평균회귀 매도 신호입니다."
        rsi_ok = rsi2 is not None and float(rsi2) > 90

    reasons = [
        _r("RSI(2) (매수<10, 매도>90)", _fmt(rsi2, 1), "pass" if rsi_ok else "warn"),
        _r("200봉 SMA (추세 필터)", _fmt(trend_sma, 0), "neutral"),
        _r("거래량 비율", _vol(vol), "neutral"),
    ]
    return SignalExplanation(
        signal_id=signal_id,
        confidence=confidence,
        summary=summary,
        reasons=reasons,
        warnings=[
            "RSI(2) 전략은 급격한 추세 전환 시 연속 신호가 발생할 수 있습니다.",
            _ADVISORY,
        ],
    )


def _unknown(
    signal_id: str,
    direction: str,  # noqa: ARG001
    ind: dict[str, Any],  # noqa: ARG001
    confidence: int,
) -> SignalExplanation:
    return SignalExplanation(
        signal_id=signal_id,
        confidence=confidence,
        summary="알 수 없는 전략 모드입니다.",
        reasons=[],
        warnings=[_ADVISORY],
    )
