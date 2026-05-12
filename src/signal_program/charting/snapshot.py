"""차트 스냅샷 생성 — DESIGN.md §5.4.

generate_snapshot: 직전 80봉 캔들 + BB 3선 + CCI 서브플롯 → PNG
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

import matplotlib

matplotlib.use("Agg")  # 서버/헤드리스 환경 호환 — import 직후 즉시 설정
import matplotlib.pyplot as plt

if TYPE_CHECKING:
    import pandas as pd

    from signal_program.models import Signal

_CANDLES_REQUIRED = 80


def generate_snapshot(
    candles: pd.DataFrame,
    signal: Signal,
    output_dir: Path,
) -> Path:
    """직전 80봉 캔들 + BB 3선 + CCI 서브플롯을 1280×720 PNG로 저장.

    Args:
        candles: DataFrame (열: opened_at, open, high, low, close, volume, quote_volume)
        signal: 트리거된 Signal 객체 — 마커·파일명 결정에 사용
        output_dir: PNG 저장 디렉토리 (없으면 생성)

    Returns:
        저장된 PNG 파일 경로

    Raises:
        ValueError: 캔들 수가 80봉 미만일 때
    """
    if len(candles) < _CANDLES_REQUIRED:
        raise ValueError(f"캔들 부족: {len(candles)}봉 < {_CANDLES_REQUIRED}봉 필요")

    output_dir.mkdir(parents=True, exist_ok=True)

    from signal_program.indicators.bollinger import bollinger  # noqa: PLC0415
    from signal_program.indicators.cci import cci as calc_cci  # noqa: PLC0415

    df: pd.DataFrame = candles.tail(_CANDLES_REQUIRED).copy().reset_index(drop=True)
    bb_df = bollinger(df["close"])
    cci_series = calc_cci(df["high"], df["low"], df["close"])

    fig, (ax_price, ax_cci) = plt.subplots(
        2,
        1,
        figsize=(12.8, 7.2),
        dpi=100,
        gridspec_kw={"height_ratios": [7, 3]},
    )

    x = range(len(df))

    # ── 가격 서브플롯 ─────────────────────────────────────────────────────────
    ax_price.plot(x, df["close"].values, color="steelblue", linewidth=1.2, label="Close")
    ax_price.plot(
        x, bb_df["bb_upper"].values, ":", color="darkorange", linewidth=1.0, label="BB Upper"
    )
    ax_price.plot(
        x, bb_df["bb_middle"].values, "-", color="dimgray", linewidth=1.0, label="BB Middle"
    )
    ax_price.plot(
        x, bb_df["bb_lower"].values, ":", color="darkorange", linewidth=1.0, label="BB Lower"
    )

    # 트리거 봉 마커
    trigger_x = len(df) - 1
    trigger_price = float(df["close"].iloc[-1])
    offset = trigger_price * 0.012
    if signal.direction.value == "buy":
        ax_price.scatter(
            [trigger_x],
            [trigger_price - offset],
            marker="^",
            color="green",
            s=120,
            zorder=5,
            label="BUY",
        )
    else:
        ax_price.scatter(
            [trigger_x],
            [trigger_price + offset],
            marker="v",
            color="red",
            s=120,
            zorder=5,
            label="SELL",
        )

    ax_price.set_title(
        f"{signal.market} — Mode {signal.mode.value} "
        f"{signal.direction.value.upper()} ({signal.strength.value.capitalize()})"
    )
    ax_price.set_ylabel("Price (KRW)")
    ax_price.legend(fontsize=7, loc="upper left")
    ax_price.grid(True, alpha=0.3)
    ax_price.tick_params(labelbottom=False)

    # ── CCI 서브플롯 ──────────────────────────────────────────────────────────
    ax_cci.plot(x, cci_series.values, color="purple", linewidth=1.0)
    for level, color in [(100, "red"), (-100, "green"), (200, "red"), (-200, "green")]:
        ax_cci.axhline(y=level, linestyle=":", color=color, alpha=0.55, linewidth=0.8)
    ax_cci.axhline(y=0, linestyle="-", color="gray", alpha=0.3, linewidth=0.5)
    ax_cci.set_ylabel("CCI(20)")
    ax_cci.grid(True, alpha=0.3)

    plt.tight_layout(pad=0.5)

    ts_str = signal.triggered_at.strftime("%Y%m%dT%H%M")
    safe_market = signal.market.replace("-", "_")
    out_path = output_dir / f"{safe_market}_{ts_str}.png"

    fig.savefig(out_path, dpi=100, format="png")
    plt.close(fig)

    return out_path
