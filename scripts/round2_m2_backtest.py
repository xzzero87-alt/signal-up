"""ADR-0030 필수 검증 — M2(12-1 모멘텀 top10) PIT 백테스트 독립 재현.

data/candles/ 캐시와 scripts/round2_pool.csv만으로 자체 완결 실행 (엔진 미사용, pandas만).
- 유니버스: 연도별 전년 12월 일평균 거래대금 top50 (point-in-time)
- 전략: 매월 말 12-1 모멘텀 top10 동일가중, 익일부터 보유, 비용 = 턴오버×편도비용
- 벤치 1: PIT-EW50 (연도별 유니버스 동일가중)
- 벤치 2: KODEX200(069500) B&H — 캐시에 있으면 자동 포함 (시총가중 지수 프록시)

실행:  uv run python scripts/round2_m2_backtest.py
산출:  reports/compare/round2/round2_repro.csv + 콘솔 표
대조:  reports/compare/round2/round2_results.csv (Cowork 샌드박스 원본)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path("data/candles")
POOL = Path("scripts/round2_pool.csv")
OUT = Path("reports/compare/round2")
IS_START, IS_END = "2022-03-02", "2025-12-30"
OOS_START, OOS_END = "2026-01-02", "2026-07-08"
KOSPI200_ETF = "069500"


def load_matrix() -> tuple[pd.DataFrame, pd.DataFrame]:
    codes = pd.read_csv(POOL, dtype=str)["code"].tolist()
    closes, qvs = {}, {}
    for code in codes + [KOSPI200_ETF]:
        d = BASE / code / "1440"
        files = sorted(d.glob("*.parquet")) if d.exists() else []
        if not files:
            continue
        df = pd.concat(
            pd.read_parquet(p, columns=["opened_at", "close", "quote_volume"]) for p in files
        )
        df = df.set_index("opened_at").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        closes[code], qvs[code] = df["close"], df["quote_volume"]
    px = pd.DataFrame(closes)
    px.index = pd.DatetimeIndex(px.index).tz_localize(None)
    px = px.sort_index()
    qv = pd.DataFrame(qvs).set_axis(px.index)
    return px, qv


def build_universes(qv: pd.DataFrame, pool_codes: list[str]) -> dict[int, list[str]]:
    uni = {}
    for year in (2022, 2023, 2024, 2025, 2026):
        dec = qv.loc[f"{year - 1}-12", pool_codes]
        avg = dec.mean().dropna()
        avg = avg[dec.notna().sum() >= 10]
        uni[year] = list(avg.nlargest(50).index)
    return uni


def month_ends(idx: pd.DatetimeIndex) -> list[pd.Timestamp]:
    return list(pd.Series(idx, index=idx).groupby(idx.to_period("M")).max())


def run_m2(px, rets, uni, start, end, cost, n=10):
    mes = [d for d in month_ends(px.index) if d < pd.Timestamp(end)]
    w = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    for i, d in enumerate(mes):
        if d < pd.Timestamp(start) - pd.Timedelta(days=40):
            continue
        nxt = px.index[px.index > d]
        if not len(nxt):
            break
        u = uni.get(nxt[0].year)
        if u is None:
            continue
        idx = px.index.get_indexer([d], method="ffill")[0]
        if idx - 252 < 0:
            continue
        mom = (px.iloc[idx - 21] / px.iloc[idx - 252] - 1)[u].dropna()
        top = mom.nlargest(min(n, len(mom)))
        stop = mes[i + 1] if i + 1 < len(mes) else px.index[-1]
        mask = (px.index >= nxt[0]) & (px.index <= stop)
        for c in top.index:
            w.loc[mask, c] = 1.0 / n
    net = (w.shift(1) * rets).sum(axis=1) - w.diff().abs().sum(axis=1) * cost
    return net.loc[start:end]


def stats(net: pd.Series, bench: pd.Series, label: str, window: str) -> dict:
    cum = (1 + net).prod() - 1
    bcum = (1 + bench).prod() - 1
    sh = net.mean() / net.std() * np.sqrt(252) if net.std() > 0 else 0.0
    bsh = bench.mean() / bench.std() * np.sqrt(252) if bench.std() > 0 else 0.0
    eq = (1 + net).cumprod()
    mdd = (eq / eq.cummax() - 1).min()
    row = {"strategy": label, "window": window, "cum": f"{cum:+.1%}",
           "bench_cum": f"{bcum:+.1%}", "sharpe": round(float(sh), 2),
           "bench_sharpe": round(float(bsh), 2), "mdd": f"{mdd:.1%}"}
    for y in (2022, 2023, 2024, 2025):
        yr = net.loc[str(y)] if str(y) in net.index.strftime("%Y") else pd.Series(dtype=float)
        if len(yr):
            row[f"y{y}"] = f"{(1 + yr).prod() - 1:+.0%}/{(1 + bench.loc[str(y)]).prod() - 1:+.0%}"
    return row


def main() -> None:
    px, qv = load_matrix()
    pool_codes = [c for c in pd.read_csv(POOL, dtype=str)["code"] if c in px.columns]
    print(f"[데이터] {len(pool_codes)}종 (+KODEX200 {'있음' if KOSPI200_ETF in px.columns else '없음'}), "
          f"{px.index.min().date()} ~ {px.index.max().date()}")
    rets = px.pct_change()
    uni = build_universes(qv, pool_codes)

    bench = pd.Series(0.0, index=px.index)
    for y, u in uni.items():
        mask = px.index.year == y
        bench[mask] = rets.loc[mask, u].mean(axis=1)

    rows = []
    for start, end, window in ((IS_START, IS_END, "IS_2022-03~2025-12"),
                               (OOS_START, OOS_END, "OOS_2026-01~2026-07-08")):
        b = bench.loc[start:end]
        for cost in (0.001, 0.003):
            net = run_m2(px, rets, uni, start, end, cost)
            rows.append(stats(net, b, f"M2_PIT_top10_c{cost:.1%}", window))
        if KOSPI200_ETF in px.columns:
            k = rets[KOSPI200_ETF].loc[start:end]
            rows.append(stats(k, b, "KODEX200_B&H(시총가중_프록시)", window))

    out = pd.DataFrame(rows)
    print(out.to_string(index=False))
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT / "round2_repro.csv", index=False, encoding="utf-8-sig")
    print(f"\n[저장] {OUT / 'round2_repro.csv'} — round2_results.csv(샌드박스 원본)와 대조하세요.")


if __name__ == "__main__":
    main()
