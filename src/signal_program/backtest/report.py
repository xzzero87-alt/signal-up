"""백테스트 HTML 리포트 렌더러 — DESIGN.md §6.5.

BacktestReportRenderer: Jinja2 템플릿 → 자기완결 HTML (외부 CDN 0개)
차트 헬퍼: matplotlib Agg 백엔드, base64 인라인 PNG (800×400, dpi=80)
MDD 컨벤션: 모델 음수, 표시 abs() (M10 follow-up 규약)
Sharpe: 부호 그대로 표시

import 사용처:
  - cli.py backtest --report-html
  - M15 GUI 백테스트 페이지
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from datetime import datetime  # noqa: TC003
from pathlib import Path  # noqa: TC003

import matplotlib
import matplotlib.ticker as mticker

matplotlib.use("Agg")  # 서버/헤드리스 호환 — snapshot.py 동일 패턴
import matplotlib.pyplot as plt

from signal_program.backtest.metrics import BacktestResult, TradeRecord  # noqa: TC001

# ── 차트 헬퍼 ────────────────────────────────────────────────────────────────

def _empty_png_base64() -> str:
    """빈 차트 → base64 PNG (trades 없을 때 안전 폴백)."""
    fig, ax = plt.subplots(figsize=(8, 4), dpi=80)
    ax.text(0.5, 0.5, "No trades", ha="center", va="center", transform=ax.transAxes, color="#999")
    ax.set_axis_off()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def equity_curve_png_base64(trades: tuple[TradeRecord, ...]) -> str:
    """누적 수익률 곡선 PNG → base64. trades 빈 경우 빈 차트 반환."""
    if not trades:
        return _empty_png_base64()

    equity = 1.0
    cum: list[float] = [0.0]
    for t in trades:
        equity *= 1 + t.pnl_pct
        cum.append(equity - 1.0)

    xs = list(range(len(cum)))
    fig, ax = plt.subplots(figsize=(8, 4), dpi=80)
    ax.plot(xs, [v * 100 for v in cum], color="#1565C0", linewidth=1.2)
    ax.axhline(0, color="#bbb", linewidth=0.6, linestyle="--")
    ax.fill_between(
        xs,
        [v * 100 for v in cum],
        0,
        where=[v < 0 for v in cum],
        alpha=0.15,
        color="#c62828",
    )
    ax.fill_between(
        xs,
        [v * 100 for v in cum],
        0,
        where=[v >= 0 for v in cum],
        alpha=0.15,
        color="#2e7d32",
    )
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:.1f}%"))
    ax.set_title("Equity Curve", fontsize=11)
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Cumulative Return (%)")
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def drawdown_png_base64(trades: tuple[TradeRecord, ...]) -> str:
    """Drawdown 시각화 PNG → base64. trades 빈 경우 빈 차트 반환."""
    if not trades:
        return _empty_png_base64()

    equity = 1.0
    eq_curve: list[float] = [1.0]
    for t in trades:
        equity *= 1 + t.pnl_pct
        eq_curve.append(equity)

    peak = eq_curve[0]
    dds: list[float] = [0.0]
    for eq in eq_curve[1:]:
        if eq > peak:
            peak = eq
        dd = (eq - peak) / peak * 100 if peak > 0 else 0.0
        dds.append(dd)

    xs = list(range(len(dds)))
    fig, ax = plt.subplots(figsize=(8, 4), dpi=80)
    ax.fill_between(xs, dds, 0, color="#c62828", alpha=0.4)
    ax.plot(xs, dds, color="#c62828", linewidth=0.8)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:.1f}%"))
    ax.set_title("Drawdown", fontsize=11)
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Drawdown (%)")
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


# ── 렌더러 ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BacktestReportRenderer:
    """Jinja2 기반 HTML 리포트 렌더러. autoescape=True 강제로 XSS 방어."""

    template_dir: Path

    def render_html(
        self,
        result: BacktestResult,
        *,
        market: str,
        mode_label: str,
        generated_at: datetime,
    ) -> str:
        """HTML 문자열 반환. 호출자가 파일로 쓴다."""
        from jinja2 import Environment, FileSystemLoader

        env = Environment(
            autoescape=True,
            loader=FileSystemLoader(str(self.template_dir)),
        )
        template = env.get_template("backtest_report.html.j2")

        return str(
            template.render(
                result=result,
                market=market,
                mode_label=mode_label,
                generated_at=generated_at,
                fmt_win_rate=f"{result.win_rate:.1%}",
                fmt_avg_pnl=f"{result.avg_pnl_pct:+.2%}",
                fmt_cumulative=f"{result.cumulative_return_pct:+.2%}",
                fmt_mdd=f"{abs(result.mdd_pct):.2%}",
                fmt_sharpe=f"{result.sharpe_annualized:.2f}",
                fmt_avg_bars=f"{result.avg_bars_held:.1f}",
                equity_curve_b64=equity_curve_png_base64(result.trades),
                drawdown_b64=drawdown_png_base64(result.trades),
            )
        )
