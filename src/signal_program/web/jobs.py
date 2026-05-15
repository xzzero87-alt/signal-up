"""백테스트 잡 큐 — M15.

BacktestJobManager: asyncio.Queue + worker 1개 + timeout 15분 + max 5건
JobRecord: dataclass (frozen, slots)
JobSpec: dataclass (frozen, slots)

DI: app.state.job_manager (lifespan에서 초기화)
CPU-bound engine은 asyncio.to_thread()로 실행 (이벤트 루프 블록 방지)
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from signal_program.state.settings_store import SettingsStore

# ── 타입 ────────────────────────────────────────────────────────────────────


class JobKind(StrEnum):
    BACKTEST = "backtest"
    WALKFORWARD = "walkforward"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


# ── 예외 ─────────────────────────────────────────────────────────────────────


class JobQueueFullError(Exception):
    """잡 큐가 MAX_QUEUE_LEN에 도달했을 때 발생."""


class BacktestDataError(Exception):
    """캔들 캐시 미스 또는 데이터 부족 오류."""


# ── 데이터 모델 ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class JobSpec:
    kind: JobKind
    market: str
    period_from: datetime
    period_to: datetime
    mode: str  # "A" | "B" | "both"
    train_months: int | None = None
    validate_months: int | None = None
    grid_str: str | None = None


@dataclass(frozen=True, slots=True)
class JobRecord:
    job_id: str
    kind: JobKind
    status: JobStatus
    submitted_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    market: str
    period_from: datetime
    period_to: datetime
    mode: str
    result_path: Path | None
    error_message: str | None


# ── path traversal 헬퍼 ──────────────────────────────────────────────────────


def _is_safe_report_path(job_id: str, reports_dir: Path) -> bool:
    """job_id가 reports_dir/jobs/ 안에 있고 path traversal이 없는지 확인."""
    try:
        safe_path = (reports_dir / "jobs" / f"{job_id}.html").resolve()
        return safe_path.is_relative_to(reports_dir.resolve())
    except (ValueError, OSError):
        return False


# ── JobManager ───────────────────────────────────────────────────────────────

JobExecutor = Callable[[JobSpec, Path], None]


class BacktestJobManager:
    """asyncio 잡 큐 매니저. 동시 실행 1건 제한. 인메모리 상태."""

    MAX_QUEUE_LEN = 5
    JOB_TIMEOUT_SEC = 900.0

    def __init__(
        self,
        reports_dir: Path,
        candles_cache_root: Path,
        settings_store: SettingsStore | None,
        *,
        _executor: JobExecutor | None = None,
        job_timeout_sec: float | None = None,
    ) -> None:
        self._reports_dir = reports_dir
        self._candles_root = candles_cache_root
        self._store = settings_store
        self._executor = _executor
        self._timeout = job_timeout_sec if job_timeout_sec is not None else self.JOB_TIMEOUT_SEC
        self._jobs: dict[str, JobRecord] = {}
        self._ordered: list[str] = []
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """워커 태스크 기동. lifespan startup에서 호출."""
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        """워커 태스크 취소. lifespan shutdown에서 호출."""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            import contextlib

            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task

    async def submit(self, spec: JobSpec) -> JobRecord:
        """잡 큐잉. MAX_QUEUE_LEN 초과 시 JobQueueFullError 발생."""
        active = sum(
            1 for r in self._jobs.values() if r.status in (JobStatus.QUEUED, JobStatus.RUNNING)
        )
        if active >= self.MAX_QUEUE_LEN:
            raise JobQueueFullError

        job_id = uuid.uuid4().hex
        record = JobRecord(
            job_id=job_id,
            kind=spec.kind,
            status=JobStatus.QUEUED,
            submitted_at=datetime.now(tz=UTC),
            started_at=None,
            finished_at=None,
            market=spec.market,
            period_from=spec.period_from,
            period_to=spec.period_to,
            mode=spec.mode,
            result_path=None,
            error_message=None,
        )
        self._jobs[job_id] = record
        self._ordered.append(job_id)
        await self._queue.put(job_id)
        return record

    def list_recent(self, limit: int = 20) -> list[JobRecord]:
        """최근 잡 목록 (제출 내림차순)."""
        return [self._jobs[jid] for jid in reversed(self._ordered) if jid in self._jobs][:limit]

    def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    @property
    def reports_dir(self) -> Path:
        return self._reports_dir

    def _update(self, job_id: str, **kwargs: Any) -> None:
        self._jobs[job_id] = replace(self._jobs[job_id], **kwargs)

    async def _worker(self) -> None:
        """순차 처리 워커. timeout/exception 처리 후 결과 저장."""
        while True:
            job_id = await self._queue.get()
            if job_id not in self._jobs:
                self._queue.task_done()
                continue

            record = self._jobs[job_id]
            self._update(job_id, status=JobStatus.RUNNING, started_at=datetime.now(tz=UTC))

            spec = JobSpec(
                kind=record.kind,
                market=record.market,
                period_from=record.period_from,
                period_to=record.period_to,
                mode=record.mode,
                train_months=None,
                validate_months=None,
                grid_str=None,
            )
            output_path = self._reports_dir / "jobs" / f"{job_id}.html"
            output_path.parent.mkdir(parents=True, exist_ok=True)

            fn = self._executor if self._executor is not None else self._build_executor()

            try:
                await asyncio.wait_for(
                    asyncio.to_thread(fn, spec, output_path),
                    timeout=self._timeout,
                )
                self._update(
                    job_id,
                    status=JobStatus.SUCCEEDED,
                    finished_at=datetime.now(tz=UTC),
                    result_path=output_path,
                )
            except TimeoutError:
                self._update(
                    job_id,
                    status=JobStatus.FAILED,
                    finished_at=datetime.now(tz=UTC),
                    error_message="시간 초과",
                )
            except Exception as exc:  # noqa: BLE001
                self._update(
                    job_id,
                    status=JobStatus.FAILED,
                    finished_at=datetime.now(tz=UTC),
                    error_message=str(exc),
                )
            finally:
                self._queue.task_done()

    def _build_executor(self) -> JobExecutor:
        """실 구현 executor: 캔들 로드 → 엔진 실행 → HTML 저장."""
        store = self._store
        candles_root = self._candles_root

        def execute(spec: JobSpec, output_path: Path) -> None:
            from datetime import timedelta
            from zoneinfo import ZoneInfo

            import pandas as pd

            from signal_program.backtest.candles_io import load_candles
            from signal_program.backtest.engine import BacktestEngine
            from signal_program.backtest.report import _TEMPLATE_DIR, BacktestReportRenderer
            from signal_program.backtest.walkforward import WalkforwardEngine, parse_grid
            from signal_program.strategies.bb_cci import BbCciStrategy

            kst = ZoneInfo("Asia/Seoul")
            settings = store.load() if store is not None else None

            period_from = spec.period_from
            period_to = spec.period_to
            all_candles = []
            cur = period_from.replace(day=1)
            while cur < period_to:
                month_str = cur.strftime("%Y-%m")
                path = candles_root / spec.market / "60" / f"{month_str}.parquet"
                if path.exists():
                    all_candles.extend(load_candles(path))
                cur = (cur + timedelta(days=32)).replace(day=1)

            filtered = [c for c in all_candles if period_from <= c.opened_at < period_to]
            filtered.sort(key=lambda c: c.opened_at)

            if not filtered:
                raise BacktestDataError(
                    f"이 기간의 캔들 데이터가 없습니다. CLI에서 "
                    f"`uv run signal fetch-candles --market {spec.market} "
                    f"--from {period_from.date()} --to {period_to.date()}` 먼저 실행하세요."
                )

            def _s(attr: str, default: Any) -> Any:
                return getattr(settings, attr, default) if settings is not None else default

            strategy = BbCciStrategy(
                bb_period=_s("bb_period", 20),
                bb_std_mult=_s("bb_std_mult", 2.0),
                cci_period=_s("cci_period", 20),
                cci_threshold_normal=_s("cci_threshold_normal", 100),
                cci_threshold_strong=_s("cci_threshold_strong", 200),
                volume_ratio_min_a=_s("volume_ratio_min_a", 1.0),
                volume_ratio_min_b=_s("volume_ratio_min_b", 1.5),
                squeeze_lookback=_s("squeeze_lookback", 120),
                squeeze_quantile=_s("squeeze_quantile", 0.20),
            )
            base_engine = BacktestEngine(strategy=strategy)
            generated_at = datetime.now(tz=kst)

            if spec.kind == JobKind.WALKFORWARD:
                grid_str = spec.grid_str or "bb_std_mult:1.5,2.0,2.5"
                param_grid = parse_grid(grid_str)
                wf_engine = WalkforwardEngine(
                    backtest_engine=base_engine,
                    candles_cache_root=candles_root,
                    param_grid=param_grid,
                )
                wf_result = wf_engine.run(
                    market=spec.market,
                    period_from=period_from,
                    period_to=period_to,
                    train_months=spec.train_months or 8,
                    validate_months=spec.validate_months or 2,
                )
                from signal_program.backtest.report import walkforward_render_html

                html = walkforward_render_html(
                    wf_result,
                    market=spec.market,
                    mode_label=f"{spec.mode} (grid={grid_str})",
                    generated_at=generated_at,
                    template_dir=_TEMPLATE_DIR,
                )
            else:
                df = pd.DataFrame([c.model_dump() for c in filtered])
                result = base_engine.run(spec.market, df)
                renderer = BacktestReportRenderer(template_dir=_TEMPLATE_DIR)
                html = renderer.render_html(
                    result,
                    market=spec.market,
                    mode_label=spec.mode,
                    generated_at=generated_at,
                )

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(html, encoding="utf-8")

        return execute
