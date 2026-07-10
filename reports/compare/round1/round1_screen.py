"""Round 1 스크리닝 — Track 1(모멘텀/선택) + Track 2(타이밍) 포트폴리오 백테스트.

사전 등록 후보 (2026-07-09, 실행 전 고정):
  M1: 12-1 모멘텀 top5   M2: 12-1 top10   M3: 6-1 top5
  M4: 52주고점 근접 top5  M5: 듀얼모멘텀(M2+절대필터<0 → 현금)
  D1: EW지수 200일 SMA 타이밍 (하회 시 전량 현금)
  C1: D1 타이밍 + 상회 시 M2 보유
벤치마크: EW43 B&H (일별 동일가중 리밸런스 지수)
비용: 리밸런스 시 턴오버 × 0.2% (편도 0.1% = 수수료 0.05%+슬리피지 0.05%, 엔진 패리티)
판정창(인샘플): 2022-03-02 ~ 2025-12-30.  2026년은 봉인 (OOS, 파이널리스트만).
"""
import pandas as pd
import numpy as np
import pathlib
import sys

BASE = pathlib.Path("/sessions/keen-inspiring-faraday/mnt/signal-up/data/candles")
CODES = ("005930 000660 009150 018260 066570 373220 006400 247540 086520 051910 "
         "010130 005490 035420 035720 259960 036570 251270 263750 293490 041510 "
         "035900 005380 000270 012330 207940 068270 196170 028300 105560 055550 "
         "086790 032830 000810 028260 003550 034730 017670 030200 015760 096770 "
         "010950 011200 090430").split()
COST_PER_SIDE = 0.001  # 0.1%
IS_START, IS_END = "2022-03-02", "2025-12-30"
OOS_START, OOS_END = "2026-01-02", "2026-07-08"


def load_closes() -> pd.DataFrame:
    frames = {}
    for c in CODES:
        d = BASE / c / "1440"
        df = pd.concat(pd.read_parquet(p) for p in sorted(d.glob("*.parquet")))
        s = df.set_index("opened_at")["close"].sort_index()
        s = s[~s.index.duplicated(keep="last")]
        frames[c] = s
    px = pd.DataFrame(frames)
    px.index = pd.DatetimeIndex(px.index).tz_localize(None)
    return px.sort_index()


def month_ends(idx: pd.DatetimeIndex) -> list:
    return list(pd.Series(idx, index=idx).groupby(idx.to_period("M")).max())


def run_portfolio(px: pd.DataFrame, pick_fn, timing=None, start=IS_START, end=IS_END):
    """월말 종가 기준 선정 → 익일부터 보유. pick_fn(date)->dict{code:weight}. timing(date)->0/1 노출."""
    rets = px.pct_change()
    mes = [d for d in month_ends(px.index) if d < pd.Timestamp(end)]
    weights = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    current = {}
    for i, d in enumerate(mes):
        if d < pd.Timestamp(start) - pd.Timedelta(days=40):
            continue
        w = pick_fn(d) or {}
        if timing is not None and timing(d) == 0:
            w = {}
        nxt = px.index[px.index > d]
        if len(nxt) == 0:
            break
        n0 = nxt[0]
        stop = mes[i + 1] if i + 1 < len(mes) else px.index[-1]
        mask = (px.index >= n0) & (px.index <= stop)
        for c, wt in w.items():
            weights.loc[mask, c] = wt
        current = w
    port_ret = (weights.shift(1) * rets).sum(axis=1)  # weight는 당일 보유분 — shift로 익일 수익 귀속
    turnover = weights.diff().abs().sum(axis=1)
    cost = turnover * COST_PER_SIDE
    net = port_ret - cost
    return net.loc[start:end]


def momentum(px, d, lb_long, lb_skip):
    """lb_skip 전 시점까지 lb_long 기간 수익률."""
    idx = px.index.get_indexer([d], method="ffill")[0]
    if idx - lb_long < 0:
        return None
    p_now = px.iloc[idx - lb_skip]
    p_then = px.iloc[idx - lb_long]
    mom = p_now / p_then - 1
    return mom.dropna()


def topn_weights(scores, n):
    if scores is None or len(scores) < n:
        return {}
    top = scores.nlargest(n)
    return {c: 1.0 / n for c in top.index}


def make_pick(px, lb_long, lb_skip, n, abs_filter=False):
    def pick(d):
        mom = momentum(px, d, lb_long, lb_skip)
        if mom is None:
            return {}
        if abs_filter:
            mom = mom[mom > 0]
        return topn_weights(mom, n) if len(mom) >= n else (
            {c: 1.0 / n for c in mom.nlargest(len(mom)).index} if abs_filter and len(mom) > 0 else {})
    return pick


def make_w52(px, n):
    def pick(d):
        idx = px.index.get_indexer([d], method="ffill")[0]
        if idx < 252:
            return {}
        win = px.iloc[idx - 252:idx + 1]
        ratio = (win.iloc[-1] / win.max()).dropna()
        return topn_weights(ratio, n)
    return pick


def stats(net, bench, label, years=("2022", "2023", "2024", "2025")):
    cum = (1 + net).prod() - 1
    bcum = (1 + bench).prod() - 1
    sharpe = net.mean() / net.std() * np.sqrt(252) if net.std() > 0 else 0
    eq = (1 + net).cumprod()
    mdd = (eq / eq.cummax() - 1).min()
    beq = (1 + bench).cumprod()
    bmdd = (beq / beq.cummax() - 1).min()
    yr = {}
    for y in years:
        r = net.loc[y] if y in net.index.strftime("%Y") else None
        b = bench.loc[y]
        ry = (1 + net.loc[y]).prod() - 1 if len(net.loc[y]) else np.nan
        by = (1 + b).prod() - 1 if len(b) else np.nan
        yr[y] = (ry, by)
    row = dict(strategy=label, cum=f"{cum:+.1%}", bench_cum=f"{bcum:+.1%}",
               sharpe=round(sharpe, 2), mdd=f"{mdd:.1%}", bench_mdd=f"{bmdd:.1%}")
    for y, (ry, by) in yr.items():
        row[y] = f"{ry:+.1%}/{by:+.1%}"
    return row


def main():
    px = load_closes()
    px_is = px  # 선정용 전체(웜업 포함), 평가창은 stats에서 자름
    rets = px.pct_change()
    ew_bench = rets.mean(axis=1).loc[IS_START:IS_END]  # EW43 일별 리밸런스 지수

    # 지수 타이밍용 EW 지수·SMA200
    ew_idx = (1 + rets.mean(axis=1)).cumprod()
    sma200 = ew_idx.rolling(200).mean()
    def timing(d):
        i = ew_idx.index.get_indexer([d], method="ffill")[0]
        return 1 if ew_idx.iloc[i] > sma200.iloc[i] else 0

    ew_pick = lambda d: {c: 1.0 / len(CODES) for c in CODES}

    runs = {
        "M1_mom12-1_top5":  dict(pick=make_pick(px, 252, 21, 5)),
        "M2_mom12-1_top10": dict(pick=make_pick(px, 252, 21, 10)),
        "M3_mom6-1_top5":   dict(pick=make_pick(px, 126, 21, 5)),
        "M4_52wHigh_top5":  dict(pick=make_w52(px, 5)),
        "M5_dual_mom_top10": dict(pick=make_pick(px, 252, 21, 10, abs_filter=True)),
        "D1_EW_sma200_timing": dict(pick=ew_pick, timing=timing),
        "C1_mom12-1top10_timed": dict(pick=make_pick(px, 252, 21, 10), timing=timing),
    }
    rows = []
    for label, cfg in runs.items():
        net = run_portfolio(px, cfg["pick"], cfg.get("timing"))
        rows.append(stats(net, ew_bench, label))
    rows.append(stats(ew_bench, ew_bench, "BENCH_EW43_B&H"))
    out = pd.DataFrame(rows)
    print(out.to_string(index=False))
    out.to_csv("/tmp/round1_screening.csv", index=False)

if __name__ == "__main__":
    main()
