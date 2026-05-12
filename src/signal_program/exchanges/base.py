from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime

    from signal_program.enums import Timeframe
    from signal_program.models import Candle


class Exchange(Protocol):
    async def list_krw_markets(self) -> list[str]: ...

    async def fetch_candles(
        self,
        market: str,
        timeframe: Timeframe,
        count: int,
        to: datetime | None = None,
    ) -> list[Candle]: ...
