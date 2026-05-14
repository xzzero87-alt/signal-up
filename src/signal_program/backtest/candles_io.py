"""캔들 parquet R/W — 백테스트 캐시.

parquet 스키마:
  opened_at : datetime64[ns, Asia/Seoul]
  open      : float64
  high      : float64
  low       : float64
  close     : float64
  volume    : float64
  quote_volume : float64
  market    : string

import 사용처:
  - cli.py fetch-candles / backtest 커맨드
  - M15 GUI 백테스트 페이지
"""

from __future__ import annotations

import pathlib

from signal_program.models import Candle


def save_candles(candles: list[Candle], path: pathlib.Path) -> None:
    """캔들 리스트를 parquet으로 저장. 부모 디렉토리를 자동 생성한다."""
    raise NotImplementedError


def load_candles(path: pathlib.Path) -> list[Candle]:
    """parquet 파일에서 캔들 리스트를 로드한다. 파일이 없으면 FileNotFoundError."""
    raise NotImplementedError
