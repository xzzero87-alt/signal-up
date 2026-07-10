"""Round 2 — point-in-time 유니버스 데이터 수집 (ADR-0029 Decision 2).

각 연도 Y의 유니버스 = Y-1 마지막 거래일 기준 KOSPI+KOSDAQ 시총 상위 50
(우선주·스팩·리츠 제외). 유니버스 합집합의 일봉 OHLCV(수정주가)를 저장한다.

실행 (pyproject 변경 없음):
    uv run --with pykrx python scripts/round2_fetch_pit_data.py

산출:
    reports/compare/round2/pit_universe.csv      — 연도별 top50 구성 (point-in-time)
    reports/compare/round2/pit_ohlcv/{code}.parquet — 합집합 종목 일봉 (2021-01~2026-07)
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
from pykrx import stock

OUT = Path("reports/compare/round2")
OHLCV_DIR = OUT / "pit_ohlcv"
YEAR_END_ANCHORS = {
    2022: "20211230",
    2023: "20221229",
    2024: "20231228",
    2025: "20241230",
    2026: "20251230",
}
TOP_N = 50
FETCH_FROM, FETCH_TO = "20210101", "20260708"


def is_excluded(name: str) -> bool:
    n = name.replace(" ", "")
    return (
        n.endswith(("우", "우B", "우C", "1우", "2우B", "3우B"))
        or "스팩" in n
        or n.endswith("리츠")
    )


def top50_at(date: str) -> pd.DataFrame:
    frames = []
    for mkt in ("KOSPI", "KOSDAQ"):
        df = stock.get_market_cap_by_ticker(date, market=mkt)
        df = df.reset_index().rename(columns={"티커": "code"})
        df["market"] = mkt
        frames.append(df)
    allmkt = pd.concat(frames)
    allmkt["name"] = [stock.get_market_ticker_name(c) for c in allmkt["code"]]
    allmkt = allmkt[~allmkt["name"].map(is_excluded)]
    return allmkt.nlargest(TOP_N, "시가총액")[["code", "name", "market", "시가총액"]]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    OHLCV_DIR.mkdir(exist_ok=True)

    rows = []
    for year, anchor in YEAR_END_ANCHORS.items():
        top = top50_at(anchor)
        top.insert(0, "universe_year", year)
        top.insert(1, "anchor_date", anchor)
        rows.append(top)
        print(f"[유니버스] {year}년(기준 {anchor}): {len(top)}종")
        time.sleep(1)
    uni = pd.concat(rows, ignore_index=True)
    uni.to_csv(OUT / "pit_universe.csv", index=False, encoding="utf-8-sig")

    codes = sorted(uni["code"].unique())
    print(f"[수집 대상] 합집합 {len(codes)}종 일봉 {FETCH_FROM}~{FETCH_TO}")
    for i, code in enumerate(codes, 1):
        dest = OHLCV_DIR / f"{code}.parquet"
        if dest.exists():
            continue
        df = stock.get_market_ohlcv(FETCH_FROM, FETCH_TO, code, adjusted=True)
        if df.empty:
            print(f"  [{i}/{len(codes)}] {code}: 데이터 없음 (상장폐지/신규) — 스킵 기록")
            continue
        df = df.reset_index().rename(
            columns={"날짜": "date", "시가": "open", "고가": "high",
                     "저가": "low", "종가": "close", "거래량": "volume"}
        )
        df["code"] = code
        df.to_parquet(dest, index=False)
        if i % 10 == 0:
            print(f"  [{i}/{len(codes)}] 진행 중")
        time.sleep(0.5)  # KRX 매너 딜레이
    print("[완료] 산출물:", OUT)


if __name__ == "__main__":
    main()
