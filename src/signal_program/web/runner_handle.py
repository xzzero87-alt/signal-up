"""RunnerHandle — runner.py 라이브 루프 컨테이너 (M16).

- start/stop: 멱등하지 않음 (이미 그 상태면 RunnerStateError)
- runner 예외로 죽어도 web 생존 (_supervise가 예외 캐치)
- 5초 grace stop, 그 후 강제 cancel
- SignalHistory에서 last_signal_at 읽기 (있으면)

DI: app.state.runner_handle (lifespan에서 초기화)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable  # noqa: TC003
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from signal_program.state.signal_history import SignalHistory

_KST = ZoneInfo("Asia/Seoul")
_log = logging.getLogger(__name__)


class RunnerStateError(Exception):
    """start가 이미 running이거나 stop이 이미 stopped일 때 발생."""


@dataclass(slots=True)
class RunnerStatus:
    running: bool
    started_at: datetime | None
    last_signal_at: datetime | None
    next_poll_at: datetime | None


class RunnerHandle:
    """runner.py 라이브 루프를 감싸는 supervisor 컨테이너."""

    STOP_GRACE_SEC: float = 5.0

    def __init__(
        self,
        runner_factory: Callable[[], Awaitable[None]],
        history: SignalHistory | None = None,
        stop_grace_sec: float | None = None,
    ) -> None:
        self._factory = runner_factory
        self._history = history
        self._grace = stop_grace_sec if stop_grace_sec is not None else self.STOP_GRACE_SEC
        self._task: asyncio.Task[None] | None = None
        self._started_at: datetime | None = None
        self._running = False
        self._lock: asyncio.Lock = asyncio.Lock()

    async def start(self) -> None:
        """이미 running이면 RunnerStateError."""
        async with self._lock:
            if self._running:
                raise RunnerStateError("이미 실행 중입니다")
            self._started_at = datetime.now(tz=_KST)
            self._running = True
            self._task = asyncio.create_task(self._supervise())

    async def stop(self) -> None:
        """이미 stopped이면 RunnerStateError. grace 후 강제 cancel."""
        async with self._lock:
            if not self._running:
                raise RunnerStateError("이미 정지되어 있습니다")
            await self._cancel_task()
            self._running = False
            self._task = None

    async def stop_if_running(self) -> None:
        """이미 정지 상태면 무시."""
        if self._running:
            with contextlib.suppress(RunnerStateError):
                await self.stop()

    def status(self) -> RunnerStatus:
        last_signal_at: datetime | None = None
        if self._history is not None:
            records = self._history.read_recent(limit=1)
            if records:
                sig = records[-1].get("signal", {})
                sent_raw = sig.get("sent_at") or sig.get("timestamp")
                if sent_raw:
                    try:
                        from datetime import datetime as _dt

                        last_signal_at = _dt.fromisoformat(str(sent_raw))
                    except ValueError:
                        pass

        return RunnerStatus(
            running=self._running,
            started_at=self._started_at,
            last_signal_at=last_signal_at,
            next_poll_at=None,
        )

    async def _cancel_task(self) -> None:
        task = self._task
        if task is None or task.done():
            return
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=self._grace)
        if task not in done:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def _supervise(self) -> None:
        """factory로 코루틴 생성 후 실행. 예외 캐치 → running=False. web은 계속."""
        try:
            await self._factory()
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception("runner_crashed — web continues")
        finally:
            self._running = False
