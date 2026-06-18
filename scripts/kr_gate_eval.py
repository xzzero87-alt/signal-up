"""ADR-0022 Phase 1 게이트 집계 — kr_strategy_matrix.csv를 동일가중 유니버스로 평가.

실행: uv run python scripts/kr_gate_eval.py [--quick]

게이트 루브릭(ADR-0022):
  - 표본 충분성: 집계 거래수 >= 200 (미달 시 "결론 보류")
  - 엣지(필수): 집계 샤프 > 0  그리고  종목 누적수익 중앙값 > 종목 Buy&Hold 중앙값
  - 강건성: 연도 분할 중 과반 구간에서 집계(중앙값) 누적수익 양(+)
주: 여기서 "집계 샤프"는 종목별 샤프의 중앙값(횡단면 요약). 진짜 포트폴리오 에쿼티
곡선 기반 샤프는 후속 정제 항목.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

CSV = Path("reports/compare") / (
    "kr_strategy_matrix_quick.csv" if "--quick" in sys.argv else "kr_strategy_matrix.csv"
)
MIN_TRADES = 200


def _num(series: pd.Series) -> pd.Series:
    """'+14.74%' / '0.43' / '16' / 'NA' → float (NA→NaN)."""
    return pd.to_numeric(
        series.astype(str).str.replace("%", "", regex=False).str.replace(",", "", regex=False),
        errors="coerce",
    )


def main() -> int:
    if not CSV.exists():
        print(f"[오류] {CSV} 없음. 먼저 kr_strategy_matrix.ps1 실행.")
        return 1

    df = pd.read_csv(CSV)
    for col in ("trades", "cum_return", "sharpe", "mdd", "buy_hold"):
        df[col] = _num(df[col])

    full = df[df["period"] == "FULL"].copy()
    n = len(full)
    sum_trades = int(full["trades"].sum())
    med_sharpe = full["sharpe"].median()
    med_cum = full["cum_return"].median()
    med_bh = full["buy_hold"].median()
    beat = full["cum_return"] > full["buy_hold"]
    pct_beat = 100.0 * beat.mean() if n else 0.0

    # 강건성: 연도별 집계(중앙값) 누적수익 부호
    years = [p for p in ("2022", "2023", "2024", "2025") if (df["period"] == p).any()]
    year_med = {y: df.loc[df["period"] == y, "cum_return"].median() for y in years}
    pos_years = sum(1 for v in year_med.values() if v > 0)

    # ── 게이트 판정 ──────────────────────────────────────────────────
    chk_sample = sum_trades >= MIN_TRADES
    chk_edge = (med_sharpe > 0) and (med_cum > med_bh)
    chk_robust = pos_years >= (len(years) + 1) // 2 if years else False

    print(f"\n=== ADR-0022 Phase 1 게이트 평가 ({CSV.name}) ===")
    print(f"종목 수: {n}   |   FULL 기간: 2022-01-01 ~ 2025-12-31\n")
    print(f"{'항목':<28}{'결과':<26}{'합격선':<22}판정")
    print("-" * 88)
    print(
        f"{'표본 충분성(집계 거래수)':<24}{sum_trades:<26}{'>= ' + str(MIN_TRADES):<22}"
        f"{'OK' if chk_sample else '미달→보류'}"
    )
    print(
        f"{'집계 샤프(종목 중앙값)':<25}{med_sharpe:<26.2f}{'> 0':<22}"
        f"{'OK' if med_sharpe > 0 else 'X'}"
    )
    print(
        f"{'누적 중앙값 vs B&H 중앙값':<23}"
        f"{f'{med_cum:+.2f}% vs {med_bh:+.2f}%':<26}{'전자 > 후자':<22}"
        f"{'OK' if med_cum > med_bh else 'X'}"
    )
    print(f"{'  └ B&H 초과 종목 비율':<25}{f'{pct_beat:.0f}%':<26}{'(참고)':<22}")
    yr_str = ", ".join(f"{y}:{v:+.1f}%" for y, v in year_med.items())
    print(
        f"{'강건성(양(+) 연도 수)':<25}{f'{pos_years}/{len(years)}':<26}"
        f"{'>= 과반':<22}{'OK' if chk_robust else 'X'}"
    )
    print(f"{'  └ 연도별 중앙값':<25}{yr_str}")
    print("-" * 88)

    # ── 최종 ─────────────────────────────────────────────────────────
    if not chk_sample:
        verdict = "결론 보류 — 표본 부족(거래수 < 200). 종목/기간 확장 후 재평가."
    elif chk_edge and chk_robust:
        verdict = "GO — Phase 2 착수 자격. (국장: ADR-0023대로 라이브 일봉 전환 + ADR-0018 supersede 검토)"
    elif chk_edge or chk_robust:
        verdict = "보류 — 일부만 충족. 유니버스 기준 파라미터 재탐색(OOS로만 보고). 상한: 6라운드 또는 4주."
    else:
        verdict = "보류/NO-GO 후보 — 엣지·강건성 모두 미달. 상한 내 미달 고착 시 ADR-0017식 NO-GO."

    print(f"\n판정: {verdict}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
