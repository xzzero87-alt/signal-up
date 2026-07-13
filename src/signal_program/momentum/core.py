"""M2 순수 함수 — I/O 없음, round2_m2_backtest.py의 선정 로직과 동일해야 한다 (ADR-0031).

- build_universe: round2_m2_backtest.build_universes()의 단일 연도분 추출.
- select_top10: round2_m2_backtest.run_m2()의 12-1 모멘텀 상위 n 선정 로직 추출.
"""

from __future__ import annotations

import calendar
from datetime import timedelta
from typing import TYPE_CHECKING, cast

import pandas as pd

if TYPE_CHECKING:
    from datetime import date

# 전월 거래일수 최소 기준 — round2_m2_backtest.build_universes()와 동일(하드코딩 유지)
_MIN_DEC_TRADING_DAYS = 10


def build_universe(qv: pd.DataFrame, year: int, top_n: int = 50) -> list[str]:
    """전년 12월 일평균 거래대금 top_n 유니버스 (point-in-time).

    round2_m2_backtest.build_universes()와 동일 로직: 전년 12월 거래일 10일 미만인
    종목은 제외(신규상장·거래정지 등 이상치 배제) 후 평균 거래대금 상위 top_n을 반환.

    Args:
        qv: 종목코드 컬럼 x 일자 인덱스의 거래대금(quote_volume) DataFrame.
        year: 유니버스를 적용할 연도(유니버스 산정 기준월 = year-1년 12월).
        top_n: 상위 몇 종목을 뽑을지.

    Returns:
        거래대금 상위 top_n 종목코드 리스트(내림차순).
    """
    dec = cast("pd.DataFrame", qv.loc[f"{year - 1}-12"])
    avg = dec.mean().dropna()
    avg = avg[dec.notna().sum() >= _MIN_DEC_TRADING_DAYS]
    return list(avg.nlargest(top_n).index)


def select_top10(
    px: pd.DataFrame,
    universe: list[str],
    asof: pd.Timestamp,
    lb_long: int = 252,
    lb_skip: int = 21,
    n: int = 10,
) -> pd.DataFrame:
    """12-1 모멘텀(lb_long봉 전 대비 lb_skip봉 전 수익률) 상위 n 종목.

    round2_m2_backtest.run_m2()의 모멘텀 계산·상위 선정 로직과 동일. 이력이
    lb_long봉에 못 미치는 종목/유니버스 전체는 빈 DataFrame으로 자연 제외된다.

    Args:
        px: 종목코드 컬럼 x 일자 인덱스의 종가(close) DataFrame.
        universe: 이번 리밸런스에 적용할 유니버스(종목코드 리스트).
        asof: 모멘텀을 계산할 기준일(대개 월말 거래일).
        lb_long: 모멘텀 계산 장기 lookback 봉수(기본 252≈12개월).
        lb_skip: 최근 제외 lookback 봉수(기본 21≈1개월, "12-1"의 "-1").
        n: 상위 몇 종목을 뽑을지.

    Returns:
        code, momentum, close 컬럼을 가진 DataFrame(모멘텀 내림차순). 이력 부족 시 빈 DataFrame.
    """
    empty = pd.DataFrame(columns=["code", "momentum", "close"])
    idx_arr = px.index.get_indexer(pd.DatetimeIndex([asof]), method="ffill")
    idx = int(idx_arr[0])
    if idx < 0 or idx - lb_long < 0:
        return empty

    universe_in_px = [c for c in universe if c in px.columns]
    if not universe_in_px:
        return empty

    mom = (px.iloc[idx - lb_skip] / px.iloc[idx - lb_long] - 1)[universe_in_px].dropna()
    if mom.empty:
        return empty

    top = mom.nlargest(min(n, len(mom)))
    close = px.iloc[idx][top.index]
    return pd.DataFrame(
        {"code": top.index, "momentum": top.to_numpy(), "close": close.to_numpy()}
    ).reset_index(drop=True)


def diff_portfolio(prev: list[str], curr: list[str]) -> tuple[list[str], list[str]]:
    """이전 포트폴리오 대비 (편입, 편출) 종목 리스트.

    Args:
        prev: 직전 리밸런스 종목코드 리스트.
        curr: 이번 리밸런스 종목코드 리스트.

    Returns:
        (added, removed) — added는 curr 순서, removed는 prev 순서 유지.
    """
    prev_set, curr_set = set(prev), set(curr)
    added = [c for c in curr if c not in prev_set]
    removed = [c for c in prev if c not in curr_set]
    return added, removed


def _target_month(today: date) -> tuple[int, int]:
    """오늘 기준 "리밸런스 대상이 되는, 캘린더상 이미 종료된 달"의 (연, 월).

    오늘이 당월 마지막 캘린더일이면 당월 자신, 아니면(이미 다음 달로 넘어갔으면)
    직전 달. 휴장일 여부와 무관한 순수 캘린더 산술 — 라이브·백테스트 어느 쪽에서
    호출해도 같은 결과.
    """
    _, last_day = calendar.monthrange(today.year, today.month)
    if today.day == last_day:
        return today.year, today.month
    prev = today.replace(day=1) - timedelta(days=1)
    return prev.year, prev.month


def pending_rebalance_asof(
    candle_dates: pd.DatetimeIndex,
    today: date,
    last_rebalanced_asof: date | None,
) -> pd.Timestamp | None:
    """리밸런스가 밀려 있으면 그 대상 asof(대상월의 마지막 관측 거래일)를, 없으면 None.

    발화 조건을 "오늘이 마지막 거래일인가"(휴장일 캘린더 필요) 대신 "당월이 캘린더
    기준으로 이미 끝났는가"로 바꿔 별도 캘린더 의존 없이 정확히 판정한다:

    1. `_target_month(today)`로 "이미 종료된 달"을 계산(오늘이 그 달의 마지막
       캘린더일이거나, 이미 다음 달로 넘어간 경우).
    2. `last_rebalanced_asof`가 이미 그 달을 가리키면(같은 연·월) 처리 완료 → None.
    3. 아니면(첫 리밸런스거나, 트리거일을 놓친 캐치업) candle_dates에서 그 달의
       마지막 관측 거래일을 asof로 반환. 그 달 관측 데이터가 아예 없으면 None.

    KRX 상시 휴장일(예: 12/31)이 당월 마지막 평일과 겹치거나, 캘린더상 월말이
    주말인 경우에도 `round2_m2_backtest.month_ends()`가 계산하는 asof와 정확히
    일치한다 — "당월 종료"는 캘린더 사실이라 미래 예측이 필요 없기 때문이다.

    Args:
        candle_dates: 관측된 캔들 일자 인덱스(라이브에서는 오늘까지만 존재).
        today: 판정 시점.
        last_rebalanced_asof: 마지막으로 성공한 리밸런스의 asof 날짜(없으면 None).

    Returns:
        리밸런스할 asof(그 달의 마지막 관측 거래일), 또는 이미 처리됐거나 데이터가
        없으면 None.
    """
    target_year, target_month = _target_month(today)
    if (
        last_rebalanced_asof is not None
        and last_rebalanced_asof.year == target_year
        and last_rebalanced_asof.month == target_month
    ):
        return None

    normalized = candle_dates.normalize()
    in_target = normalized[(normalized.year == target_year) & (normalized.month == target_month)]
    if in_target.empty:
        return None
    return in_target.max()
