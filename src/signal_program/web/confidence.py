"""규칙 기반 신뢰도 점수 계산 — 순수 함수, 부작용 없음 (P2 v2.3).

score_confidence()는 피드백 통계를 외부에서 주입받아 단위 테스트가 가능하다.
엔드포인트에서 compute_feedback_stats()를 호출한 뒤 bad_rate를 여기에 전달한다.
"""

from __future__ import annotations

_BASE = 50

_STRONG_BONUS = 15
_VOL_HIGH_BONUS = 20  # volume_ratio >= 2.0
_VOL_MID_BONUS = 10  # volume_ratio >= 1.5
_CCI_EXTREME_BONUS = 10  # |CCI| >= 150 (mode A/B 전용)
_BB_EXTREME_BONUS = 10  # bb_pct_b <= 0 또는 >= 1 (mode A 전용)
_FIELDS_BONUS = 10  # bb_pct_b·cci·volume_ratio 세 필드 모두 존재
_BAD_RATE_HIGH_PENALTY = 20  # bad_rate >= 40%
_BAD_RATE_MID_PENALTY = 10  # bad_rate >= 25%

_CCI_EXTREME_THRESHOLD = 150.0
_VOL_HIGH_THRESHOLD = 2.0
_VOL_MID_THRESHOLD = 1.5
_BAD_RATE_HIGH = 40.0
_BAD_RATE_MID = 25.0


def score_confidence(
    *,
    strength: str,
    mode: str,
    volume_ratio: float | None,
    cci: float | None,
    bb_pct_b: float | None,
    bad_rate: float,
) -> int:
    """시그널 신뢰도를 0~100 정수로 반환한다.

    Args:
        strength:     "normal" | "STRONG" (대소문자 무관)
        mode:         전략 모드 코드 "A"~"F"
        volume_ratio: 거래량 비율 (없으면 None)
        cci:          CCI 값 (없으면 None)
        bb_pct_b:     BB %B 값 (없으면 None)
        bad_rate:     최근 30건 거짓신호율 0~100 (%)
    """
    score = _BASE

    if strength.upper() == "STRONG":
        score += _STRONG_BONUS

    if volume_ratio is not None:
        if volume_ratio >= _VOL_HIGH_THRESHOLD:
            score += _VOL_HIGH_BONUS
        elif volume_ratio >= _VOL_MID_THRESHOLD:
            score += _VOL_MID_BONUS

    if mode in ("A", "B") and cci is not None and abs(cci) >= _CCI_EXTREME_THRESHOLD:
        score += _CCI_EXTREME_BONUS

    if mode == "A" and bb_pct_b is not None and (bb_pct_b <= 0.0 or bb_pct_b >= 1.0):
        score += _BB_EXTREME_BONUS

    if bb_pct_b is not None and cci is not None and volume_ratio is not None:
        score += _FIELDS_BONUS

    if bad_rate >= _BAD_RATE_HIGH:
        score -= _BAD_RATE_HIGH_PENALTY
    elif bad_rate >= _BAD_RATE_MID:
        score -= _BAD_RATE_MID_PENALTY

    return max(0, min(100, score))
