"""캔들 parquet R/W — 백테스트 캐시.

parquet 스키마:
  opened_at    : datetime64[ns, Asia/Seoul]
  open         : float64
  high         : float64
  low          : float64
  close        : float64
  volume       : float64
  quote_volume : float64
  market       : string (utf8)

압축: snappy (기본)

import 사용처:
  - cli.py fetch-candles / backtest 커맨드
  - M15 GUI 백테스트 페이지
"""

from __future__ import annotations

import pathlib  # noqa: TC003
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from signal_program.models import Candle

_KST = ZoneInfo("Asia/Seoul")
_KST_STR = "Asia/Seoul"

_SCHEMA = pa.schema(
    [
        ("market", pa.string()),
        ("opened_at", pa.timestamp("ns", tz=_KST_STR)),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("volume", pa.float64()),
        ("quote_volume", pa.float64()),
    ]
)

_COL_ORDER = ["market", "opened_at", "open", "high", "low", "close", "volume", "quote_volume"]


def save_candles(candles: list[Candle], path: pathlib.Path) -> None:
    """캔들 리스트를 snappy 압축 parquet으로 저장. 부모 디렉토리를 자동 생성한다."""
    path.parent.mkdir(parents=True, exist_ok=True)

    if not candles:
        table = pa.table(
            {field.name: pa.array([], type=field.type) for field in _SCHEMA},
            schema=_SCHEMA,
        )
        pq.write_table(table, path, compression="snappy")
        return

    records = [c.model_dump() for c in candles]
    df = pd.DataFrame(records, columns=_COL_ORDER)

    # opened_at → KST-aware Timestamp
    ts_col = pd.to_datetime(df["opened_at"])
    if ts_col.dt.tz is None:
        ts_col = ts_col.dt.tz_localize(_KST_STR)
    else:
        ts_col = ts_col.dt.tz_convert(_KST_STR)
    df["opened_at"] = ts_col

    table = pa.Table.from_pandas(df[_COL_ORDER], schema=_SCHEMA, preserve_index=False)
    pq.write_table(table, path, compression="snappy")


def load_candles(path: pathlib.Path) -> list[Candle]:
    """parquet 파일에서 캔들 리스트를 로드한다. 파일이 없으면 FileNotFoundError."""
    if not path.exists():
        raise FileNotFoundError(f"Candle cache not found: {path}")

    df = pd.read_parquet(path)
    if len(df) == 0:
        return []

    df["opened_at"] = df["opened_at"].dt.tz_convert(_KST_STR)

    records: list[dict[str, Any]] = df.to_dict("records")  # type: ignore[assignment]
    result: list[Candle] = []
    for r in records:
        ts: pd.Timestamp = r["opened_at"]
        result.append(
            Candle(
                market=str(r["market"]),
                opened_at=ts.to_pydatetime(),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=float(r["volume"]),
                quote_volume=float(r["quote_volume"]),
            )
        )
    return result
