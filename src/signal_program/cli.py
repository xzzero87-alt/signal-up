"""typer 기반 CLI 골격.

엔트리포인트: signal
서브커맨드:
    doctor        환경 점검
    run           라이브 루프  [마일스톤 9]
    serve         웹 + 데몬   [마일스톤 13]
    scan-once     단발 평가   [마일스톤 9]
    backtest      백테스트    [마일스톤 10]
    fetch-candles 캔들 다운로드 [마일스톤 10]
    momentum-rebalance  M2 월간 리밸런스 수동 실행 [ADR-0031]
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from io import TextIOWrapper
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

if TYPE_CHECKING:
    from signal_program.exchanges.upbit import UpbitClient
    from signal_program.strategies.base import Strategy

import httpx
import typer
from rich.console import Console
from rich.table import Table

from signal_program.config import Settings
from signal_program.constants import STATE_DIR, STATE_SIGNALS_FILE
from signal_program.logging_config import attach_file_handler, configure_logging

app = typer.Typer(
    name="signal",
    help="업비트 KRW 마켓 BB+CCI 시그널 프로그램.",
    no_args_is_help=True,
)


def _ping_upbit() -> tuple[bool, list[str], str]:
    """업비트 API 핑 -> (성공 여부, KRW 마켓 목록, 세부 메시지)"""
    try:
        resp = httpx.get(
            "https://api.upbit.com/v1/market/all",
            params={"isDetails": "false"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            raw: list[dict[str, Any]] = resp.json()
            markets = [
                str(item.get("market", ""))
                for item in raw
                if str(item.get("market", "")).startswith("KRW-")
            ]
            return True, markets, ""
        return False, [], f"HTTP {resp.status_code}"
    except httpx.HTTPError as exc:
        return False, [], str(exc)


def _ping_telegram(token: str) -> tuple[bool, str]:
    """텔레그램 getMe 핑 -> (성공 여부, 세부 메시지)"""
    try:
        resp = httpx.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10.0,
        )
        if resp.status_code == 200:
            return True, ""
        return False, f"HTTP {resp.status_code}"
    except httpx.HTTPError as exc:
        return False, str(exc)


def _check_whitelist(
    settings: Settings,
    upbit_markets: list[str],
) -> tuple[bool, list[str]]:
    """화이트리스트 검증 -> (전부 존재 여부, 미상장 목록)"""
    krw_set = set(upbit_markets)
    missing = [m for m in settings.whitelist_markets if m not in krw_set]
    return len(missing) == 0, missing


@app.command()
def doctor() -> None:
    """환경 점검: 설정 로드 + 업비트/텔레그램 API 핑 + 화이트리스트 검증.

    종료 코드: 0 (전부 OK 또는 경고만), 1 (설정 오류), 2 (네트워크 오류)
    """
    try:
        settings = Settings()
    except SystemExit as exc:
        typer.echo(f"설정 오류: {exc}", err=True)
        raise typer.Exit(1) from exc

    configure_logging(settings)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    console = Console()
    table = Table(title="signal doctor", show_header=True, header_style="bold cyan")
    table.add_column("항목", style="dim", min_width=22)
    table.add_column("상태", min_width=10)
    table.add_column("세부 정보")

    table.add_row("설정 로드", "[green]OK[/green]", "")
    exit_code = 0

    upbit_ok, upbit_markets, upbit_detail = _ping_upbit()
    if upbit_ok:
        table.add_row("업비트 API", "[green]OK[/green]", upbit_detail)
    else:
        table.add_row("업비트 API", "[red]오류[/red]", upbit_detail)
        exit_code = 2

    if settings.telegram_bot_token:
        tg_ok, tg_detail = _ping_telegram(settings.telegram_bot_token)
        if tg_ok:
            table.add_row("텔레그램 API", "[green]OK[/green]", tg_detail)
        else:
            table.add_row("텔레그램 API", "[red]오류[/red]", tg_detail)
            if exit_code == 0:
                exit_code = 2
    else:
        table.add_row("텔레그램 API", "[yellow]경고[/yellow]", "토큰 미설정 - 알림 비활성")

    count = len(settings.whitelist_markets)
    if upbit_ok and upbit_markets:
        wl_ok, missing = _check_whitelist(settings, upbit_markets)
        if not wl_ok:
            table.add_row(
                f"화이트리스트 ({count}개)",
                "[yellow]경고[/yellow]",
                f"미상장: {', '.join(missing)}",
            )
        else:
            table.add_row(f"화이트리스트 ({count}개)", "[green]OK[/green]", "미상장: 없음")
    else:
        table.add_row(
            f"화이트리스트 ({count}개)",
            "[dim]SKIP[/dim]",
            "업비트 API 실패로 검증 불가",
        )

    console.print(table)
    raise typer.Exit(exit_code)


@app.command()
def run(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="텔레그램 송출 없이 로직만 검증")
    ] = False,
) -> None:
    """라이브 시그널 루프 실행 (헤드리스)."""
    import asyncio

    try:
        settings = Settings()
    except SystemExit as exc:
        typer.echo(f"설정 오류: {exc}", err=True)
        raise typer.Exit(1) from exc

    if dry_run:
        settings = settings.model_copy(update={"dry_run": True})

    import contextlib

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run_async(settings))


def _enabled_runners(settings: Settings) -> list[str]:
    """활성 라이브 러너 목록 — 게이트 판정 단일 소스 (run/serve 양쪽 공유).

    반환 순서는 조립·기동 순서. 코인 v1 라이브는 ADR-0028로 중단되어 기본
    coin_enabled=False → 데몬 상시 기동(모멘텀) 중에도 코인 러너는 조립되지 않음.
    """
    active: list[str] = []
    if settings.coin_enabled:
        active.append("coin")
    if settings.kr_enabled and settings.kis_app_key and settings.kis_app_secret:
        active.append("kr")
    if settings.momentum_enabled:
        active.append("momentum")
    return active


async def _run_async(settings: Settings) -> None:
    """RunnerService 조립 후 run_forever 실행."""
    import asyncio
    from datetime import timedelta

    import httpx
    from pydantic import SecretStr

    from signal_program.exchanges.upbit import UpbitClient
    from signal_program.notifiers.telegram import TelegramNotifier
    from signal_program.runner import RunnerService
    from signal_program.state.cooldown import CooldownStore
    from signal_program.state.signal_log import SignalLog
    from signal_program.strategies.bb_cci import BbCciStrategy

    configure_logging(settings)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    strategy = BbCciStrategy(
        bb_period=settings.bb_period,
        bb_std_mult=settings.bb_std_mult,
        cci_period=settings.cci_period,
        cci_threshold_normal=settings.cci_threshold_normal,
        cci_threshold_strong=settings.cci_threshold_strong,
        volume_ratio_min_a=settings.volume_ratio_min_a,
        volume_ratio_min_b=settings.volume_ratio_min_b,
        squeeze_lookback=settings.squeeze_lookback,
        squeeze_quantile=settings.squeeze_quantile,
    )
    cooldown = CooldownStore(
        path=settings.signals_log_path.parent / "cooldown.json",
        cooldown=timedelta(hours=settings.cooldown_hours),
    )
    signal_log = SignalLog(path=settings.signals_log_path)

    notifier = TelegramNotifier(
        bot_token=SecretStr(settings.telegram_bot_token),
        chat_id=settings.telegram_chat_id,
        dry_run=settings.dry_run,
    )
    on_signal_sent = None
    if settings.ai_enrichment_enabled and settings.anthropic_api_key:
        from signal_program.enrichment import AiEnrichmentService

        enricher = AiEnrichmentService(settings, notifier.send_text)
        on_signal_sent = enricher.enrich

    active = _enabled_runners(settings)
    if not active:
        logging.getLogger(__name__).warning(
            "no_live_runner_enabled — 활성 러너 없음(coin/kr/momentum 모두 비활성). "
            "라이브 루프를 시작하지 않고 종료합니다."
        )
        return

    from contextlib import AsyncExitStack

    runners: list[Any] = []
    async with AsyncExitStack() as stack:
        if "coin" in active:
            http = await stack.enter_async_context(
                httpx.AsyncClient(base_url="https://api.upbit.com", timeout=10.0)
            )
            exchange = UpbitClient(_client=http)
            runners.append(
                RunnerService(
                    settings=settings,
                    exchange=exchange,
                    strategy=strategy,
                    cooldown=cooldown,
                    notifier=notifier,
                    signal_log=signal_log,
                    charts_dir=settings.charts_dir,
                    on_signal_sent=on_signal_sent,
                )
            )
        if "kr" in active:
            from signal_program.exchanges.kis_api import KisApiAdapter
            from signal_program.kr_runner import KrStockRunnerService

            if settings.kr_strategy == "bb_cci":
                from signal_program.strategies import get_strategy

                kr_strategy = get_strategy("v1", settings)
            else:
                from signal_program.strategies.kr_fractal import KrFractalStrategy

                kr_strategy = KrFractalStrategy(
                    fractal_lookback=settings.fractal_lookback,
                    fractal_volume_threshold=settings.fractal_volume_threshold,
                    fractal_volume_strong=settings.fractal_volume_strong,
                )

            kr_exchange = await stack.enter_async_context(
                KisApiAdapter(
                    app_key=settings.kis_app_key,
                    app_secret=settings.kis_app_secret,
                    is_paper=settings.kis_is_paper,
                )
            )
            runners.append(
                KrStockRunnerService(
                    settings=settings,
                    exchange=kr_exchange,
                    strategy=kr_strategy,
                    notifier=notifier,
                    signal_log=signal_log,
                    cooldown_60m=CooldownStore(
                        path=Path("state/kr_cooldown_60m.json"),
                        cooldown=timedelta(hours=settings.kr_cooldown_hours_60m),
                    ),
                    cooldown_120m=CooldownStore(
                        path=Path("state/kr_cooldown_120m.json"),
                        cooldown=timedelta(hours=settings.kr_cooldown_hours_120m),
                    ),
                    cooldown_day=CooldownStore(
                        path=Path("state/kr_cooldown_day.json"),
                        cooldown=timedelta(hours=settings.kr_cooldown_hours_day),
                    ),
                    charts_dir=settings.charts_dir,
                )
            )
        if "momentum" in active:
            from signal_program.momentum.job import MomentumJob

            runners.append(MomentumJob(settings=settings, notifier=notifier))

        async with asyncio.TaskGroup() as tg:
            for runner in runners:
                tg.create_task(runner.run_forever())


@app.command(name="momentum-rebalance")
def momentum_rebalance(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="알림 미발송·상태 미갱신, 콘솔 출력만")
    ] = False,
    asof: Annotated[
        str | None, typer.Option("--asof", help="기준일 YYYY-MM-DD (기본: 오늘)")
    ] = None,
) -> None:
    """M2(12-1 횡단면 모멘텀) 월간 리밸런스 수동 실행 (ADR-0031)."""
    import asyncio
    import contextlib

    try:
        settings = Settings()
    except SystemExit as exc:
        typer.echo(f"설정 오류: {exc}", err=True)
        raise typer.Exit(1) from exc

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_momentum_rebalance_async(settings, dry_run, asof))


async def _momentum_rebalance_async(
    settings: Settings, dry_run: bool, asof_str: str | None
) -> None:
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo

    import pandas as pd
    from pydantic import SecretStr

    from signal_program.momentum.job import MomentumJob
    from signal_program.notifiers.telegram import TelegramNotifier

    configure_logging(settings)

    kst = ZoneInfo("Asia/Seoul")
    asof = pd.Timestamp(asof_str) if asof_str else pd.Timestamp(_dt.now(kst).date())

    notifier = TelegramNotifier(
        bot_token=SecretStr(settings.telegram_bot_token),
        chat_id=settings.telegram_chat_id,
        dry_run=dry_run or settings.dry_run,
    )
    job = MomentumJob(settings=settings, notifier=notifier)
    if not dry_run:
        await job.fetch_pool()
    result = await job.run_once(asof, dry_run=dry_run)

    console = Console()
    console.print(result["text"])
    status = " — dry-run: 알림 미발송·상태 미갱신" if dry_run else ""
    console.print(f"\n[dim]유니버스 {result['universe_size']}종{status}[/dim]")


@app.command()
def serve(
    port: Annotated[int | None, typer.Option("--port", help="웹 서버 포트")] = None,
    bind: Annotated[str | None, typer.Option("--bind", help="바인드 주소")] = None,
    start_daemon: Annotated[
        bool,
        typer.Option("--start-daemon", help="기동 시 자동으로 라이브 데몬도 함께 시작"),
    ] = False,
    log_file: Annotated[
        str,
        typer.Option("--log-file", help="데몬 로그 파일 경로 (ADR-0013)"),
    ] = "logs/daemon.log",
) -> None:
    """FastAPI 웹 대시보드 서버를 기동한다. 기본: http://127.0.0.1:8765/"""
    # ADR-0013: stdout UTF-8 강제 (Windows cp949 [E3] 해결)
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if isinstance(sys.stdout, TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    import asyncio

    from signal_program.state.settings_store import SettingsStore
    from signal_program.web.security import assert_safe_bind

    try:
        settings = Settings()
    except SystemExit as exc:
        typer.echo(f"설정 오류: {exc}", err=True)
        raise typer.Exit(1) from exc

    store = SettingsStore(path=Path("state/settings.json"), env_settings=settings)
    current = store.load()

    actual_bind = bind or current.web_bind
    actual_port = port or current.web_port

    assert_safe_bind(actual_bind, current.web_auth_password)

    configure_logging(current)
    typer.echo(f"서버 기동: http://{actual_bind}:{actual_port}/")

    import contextlib

    _pw = current.web_auth_password
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_serve_async(settings, actual_bind, actual_port, start_daemon, _pw, log_file))


async def _serve_async(
    settings: Settings,
    bind: str,
    port: int,
    start_daemon: bool,
    web_auth_password: str = "",
    log_file: str = "logs/daemon.log",
) -> None:
    """task supervisor 패턴 — runner 죽어도 web 생존."""
    import asyncio

    import uvicorn

    from signal_program.state.job_retention import cleanup_old_jobs
    from signal_program.state.signal_history import SignalHistory
    from signal_program.web.app import create_app
    from signal_program.web.runner_handle import RunnerHandle

    history = SignalHistory(Path(STATE_DIR) / STATE_SIGNALS_FILE)

    def _runner_factory():  # type: ignore[no-untyped-def]
        return _run_live_coro(settings)

    handle = RunnerHandle(runner_factory=_runner_factory, history=history)

    if start_daemon:
        await handle.start()
        attach_file_handler(Path(log_file))
        typer.echo("데몬 자동 시작 완료")

    reports_dir = Path("reports")
    app_instance = create_app(
        settings_path=Path("state/settings.json"),
        env_settings=settings,
        runner_handle=handle,
        bind=bind,
        web_auth_password=web_auth_password,
    )

    config = uvicorn.Config(app_instance, host=bind, port=port, log_config=None)
    server = uvicorn.Server(config)

    # retention 1회 실행 후 24h 주기
    _jobs_dir = reports_dir / "jobs"
    cleanup_old_jobs(_jobs_dir)

    async def _retention_loop() -> None:
        import asyncio as _asyncio

        while True:
            await _asyncio.sleep(86400)
            cleanup_old_jobs(_jobs_dir)

    retention_task = asyncio.create_task(_retention_loop())
    web_task = asyncio.create_task(server.serve())
    try:
        await web_task
    finally:
        await handle.stop_if_running()
        retention_task.cancel()


async def _run_live_coro(settings: Settings) -> None:
    """runner.py 라이브 루프 코루틴. RunnerHandle의 factory로 사용."""
    from datetime import timedelta
    from pathlib import Path

    import httpx
    from pydantic import SecretStr

    from signal_program.exchanges.upbit import UpbitClient
    from signal_program.notifiers.telegram import TelegramNotifier
    from signal_program.runner import RunnerService
    from signal_program.state.cooldown import CooldownStore
    from signal_program.state.notification_log import NotificationFailureLog
    from signal_program.state.signal_log import SignalLog
    from signal_program.strategies.bb_cci import BbCciStrategy

    strategy = BbCciStrategy(
        bb_period=settings.bb_period,
        bb_std_mult=settings.bb_std_mult,
        cci_period=settings.cci_period,
        cci_threshold_normal=settings.cci_threshold_normal,
        cci_threshold_strong=settings.cci_threshold_strong,
        volume_ratio_min_a=settings.volume_ratio_min_a,
        volume_ratio_min_b=settings.volume_ratio_min_b,
        squeeze_lookback=settings.squeeze_lookback,
        squeeze_quantile=settings.squeeze_quantile,
    )
    cooldown = CooldownStore(
        path=Path("state/cooldown.json"),
        cooldown=timedelta(hours=settings.cooldown_hours),
    )
    signal_log = SignalLog(path=settings.signals_log_path)
    failure_log = NotificationFailureLog(Path("state/notification_failures.jsonl"))

    notifier = TelegramNotifier(
        bot_token=SecretStr(settings.telegram_bot_token),
        chat_id=settings.telegram_chat_id,
        dry_run=settings.dry_run,
        failure_log=failure_log,
    )
    on_signal_sent = None
    if settings.ai_enrichment_enabled and settings.anthropic_api_key:
        from signal_program.enrichment import AiEnrichmentService

        enricher = AiEnrichmentService(settings, notifier.send_text)
        on_signal_sent = enricher.enrich

    active = _enabled_runners(settings)
    if not active:
        logging.getLogger(__name__).warning(
            "no_live_runner_enabled — 활성 러너 없음(coin/kr/momentum 모두 비활성). "
            "데몬 라이브 루프를 시작하지 않고 종료합니다."
        )
        return

    from contextlib import AsyncExitStack

    runners: list[Any] = []
    async with AsyncExitStack() as stack:
        if "coin" in active:
            http = await stack.enter_async_context(
                httpx.AsyncClient(base_url="https://api.upbit.com", timeout=10.0)
            )
            exchange = UpbitClient(_client=http)
            runners.append(
                RunnerService(
                    settings=settings,
                    exchange=exchange,
                    strategy=strategy,
                    cooldown=cooldown,
                    notifier=notifier,
                    signal_log=signal_log,
                    charts_dir=settings.charts_dir,
                    on_signal_sent=on_signal_sent,
                )
            )
        if "kr" in active:
            from signal_program.exchanges.kis_api import KisApiAdapter
            from signal_program.kr_runner import KrStockRunnerService

            kr_strategy: Strategy
            if settings.kr_strategy == "bb_cci":
                from signal_program.strategies import get_strategy

                # KR 전용 v1 평균회귀 (ADR-0024) — 코인 strategy_version과 독립
                kr_strategy = get_strategy("v1", settings)
            else:  # "fractal" — 하위호환(intraday 전용)
                from signal_program.strategies.kr_fractal import KrFractalStrategy

                kr_strategy = KrFractalStrategy(
                    fractal_lookback=settings.fractal_lookback,
                    fractal_volume_threshold=settings.fractal_volume_threshold,
                    fractal_volume_strong=settings.fractal_volume_strong,
                )

            kr_exchange = await stack.enter_async_context(
                KisApiAdapter(
                    app_key=settings.kis_app_key,
                    app_secret=settings.kis_app_secret,
                    is_paper=settings.kis_is_paper,
                )
            )
            runners.append(
                KrStockRunnerService(
                    settings=settings,
                    exchange=kr_exchange,
                    strategy=kr_strategy,
                    notifier=notifier,
                    signal_log=signal_log,
                    cooldown_60m=CooldownStore(
                        path=Path("state/kr_cooldown_60m.json"),
                        cooldown=timedelta(hours=settings.kr_cooldown_hours_60m),
                    ),
                    cooldown_120m=CooldownStore(
                        path=Path("state/kr_cooldown_120m.json"),
                        cooldown=timedelta(hours=settings.kr_cooldown_hours_120m),
                    ),
                    cooldown_day=CooldownStore(
                        path=Path("state/kr_cooldown_day.json"),
                        cooldown=timedelta(hours=settings.kr_cooldown_hours_day),
                    ),
                    charts_dir=settings.charts_dir,
                )
            )
        if "momentum" in active:
            from signal_program.momentum.job import MomentumJob

            runners.append(MomentumJob(settings=settings, notifier=notifier))

        async with asyncio.TaskGroup() as tg:
            for runner in runners:
                tg.create_task(runner.run_forever())


def _make_exchange_client(http: httpx.AsyncClient) -> UpbitClient:
    """UpbitClient 팩토리 — 테스트에서 패치 대상."""
    from signal_program.exchanges.upbit import UpbitClient

    return UpbitClient(_client=http)


def _make_strategy(strategy_version: str, settings: Settings) -> Strategy:
    """get_strategy() 래퍼 — 테스트에서 패치 대상."""
    from signal_program.strategies import get_strategy

    return get_strategy(strategy_version, settings)


@app.command(name="scan-once")
def scan_once(
    market: Annotated[str, typer.Option("--market", "-m", help="마켓 코드 (예: KRW-BTC)")],
    strategy: Annotated[str, typer.Option("--strategy", help="전략 버전 (v1~v5)")] = "v1",
) -> None:
    """단발성 단일 마켓 즉시 평가 (텔레그램 미전송)."""
    import asyncio

    try:
        settings = Settings()
    except SystemExit as exc:
        typer.echo(f"설정 오류: {exc}", err=True)
        raise typer.Exit(1) from exc

    asyncio.run(_scan_once_async(market, strategy, settings))


async def _scan_once_async(
    market: str,
    strategy_version: str,
    settings: Settings,
) -> None:
    from zoneinfo import ZoneInfo

    import httpx
    from rich.console import Console
    from rich.table import Table

    from signal_program.enums import Timeframe
    from signal_program.runner import candles_to_df

    _KST = ZoneInfo("Asia/Seoul")
    console = Console()

    # 전략 버전 검증
    try:
        strategy = _make_strategy(strategy_version, settings)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    console.print(f"[bold]scan-once[/bold]  {market}  |  전략: {strategy_version.upper()}")

    # 캔들 조회
    async with httpx.AsyncClient(base_url="https://api.upbit.com", timeout=10.0) as http:
        exchange = _make_exchange_client(http)
        try:
            candles = await exchange.fetch_candles(market, Timeframe.HOUR_1, 200)
        except Exception as exc:
            typer.echo(f"캔들 조회 실패: {exc}", err=True)
            raise typer.Exit(1) from exc

    if not candles:
        typer.echo(f"{market}: 캔들 데이터 없음", err=True)
        raise typer.Exit(1)

    df = candles_to_df(candles)
    signals = strategy.evaluate(market, df)

    if not signals:
        last_close = candles[-1].close
        console.print(f"[dim]{market}[/dim]  시그널 없음  |  현재가: {last_close:,.0f} KRW")
        return

    # 시그널 테이블 출력
    table = Table(title=f"{market} 시그널", show_lines=False)
    table.add_column("방향", style="bold")
    table.add_column("강도")
    table.add_column("모드")
    table.add_column("현재가", justify="right")
    table.add_column("평가시각")

    for sig in signals:
        table.add_row(
            sig.direction.value,
            sig.strength.value,
            sig.mode.value,
            f"{sig.price:,.0f}",
            sig.triggered_at.strftime("%H:%M KST"),
        )

    console.print(table)


@app.command()
def backtest(
    market: Annotated[str, typer.Option("--market", "-m", help="마켓 코드")],
    from_date: Annotated[str, typer.Option("--from", help="시작일 (YYYY-MM-DD)")],
    to_date: Annotated[str, typer.Option("--to", help="종료일 (YYYY-MM-DD)")],
    mode: Annotated[str, typer.Option("--mode", help="전략 모드 (A / B / A,B)")] = "A,B",
    strategy: Annotated[str, typer.Option("--strategy", help="전략 버전 (v1~v5)")] = "v1",
    report_html: Annotated[
        str,
        typer.Option("--report-html", help="HTML 리포트 출력 경로 (미지정 시 콘솔만)"),
    ] = "",
    grid: Annotated[
        str,
        typer.Option(
            "--grid",
            help=(
                "파라미터 그리드 (예: obv_weight:0.3,0.4,0.5;buy_threshold:0.60,0.65,0.70). "
                "지정 시 전체 조합 비교표 출력 + state/backtest/ JSON 저장."
            ),
        ),
    ] = "",
    max_hold: Annotated[
        int,
        typer.Option("--max-hold", help="최대 보유 봉 수 (기본 24)"),
    ] = 24,
    timeframe: Annotated[
        str,
        typer.Option("--timeframe", help="캔들 타임프레임: 60 (1시간봉, 기본) / 1440 (일봉)"),
    ] = "60",
    warmup_days: Annotated[
        int,
        typer.Option(
            "--warmup-days",
            help="지표 선행용 --from 이전 일수 (기본 0, 거래·지표 집계는 --from~--to만)",
        ),
    ] = 0,
) -> None:
    """저장된 parquet 캔들로 백테스트를 실행하고 결과를 표로 출력한다."""
    import asyncio

    report_path = Path(report_html) if report_html else None

    try:
        settings = Settings()
    except SystemExit as exc:
        typer.echo(f"설정 오류: {exc}", err=True)
        raise typer.Exit(1) from exc

    configure_logging(settings)
    asyncio.run(
        _backtest_async(
            settings,
            market,
            from_date,
            to_date,
            mode,
            strategy,
            report_path,
            grid,
            max_hold,
            timeframe,
            warmup_days,
        )
    )


async def _backtest_async(
    settings: Settings,
    market: str,
    from_date: str,
    to_date: str,
    mode_str: str,
    strategy_version: str = "v1",
    report_path: Path | None = None,
    grid_str: str = "",
    max_hold: int = 24,
    timeframe: str = "60",
    warmup_days: int = 0,
) -> None:
    from datetime import datetime as _dt
    from datetime import timedelta as _td
    from pathlib import Path
    from zoneinfo import ZoneInfo

    import pandas as pd

    from signal_program.backtest.candles_io import load_candles
    from signal_program.backtest.engine import BacktestEngine
    from signal_program.strategies import get_strategy

    kst = ZoneInfo("Asia/Seoul")
    start = _dt.strptime(from_date, "%Y-%m-%d").replace(tzinfo=kst)
    end = _dt.strptime(to_date, "%Y-%m-%d").replace(tzinfo=kst) + _td(days=1)
    warmup_start = start - _td(days=warmup_days) if warmup_days > 0 else start

    # 월 단위 parquet 로드 (timeframe 서브디렉토리) — warmup_days 지정 시 --from 이전 월도 포함
    all_candles = []
    cur = warmup_start.replace(day=1)
    while cur < end:
        month_str = cur.strftime("%Y-%m")
        path = Path(f"data/candles/{market}/{timeframe}/{month_str}.parquet")
        if path.exists():
            all_candles.extend(load_candles(path))
        cur = (cur + _td(days=32)).replace(day=1)

    windowed_candles = [c for c in all_candles if warmup_start <= c.opened_at < end]
    windowed_candles.sort(key=lambda c: c.opened_at)

    # 리포트/빈 데이터 판정은 항상 --from~--to 구간만 대상 (warmup 봉은 집계에서 제외)
    candles = [c for c in windowed_candles if start <= c.opened_at < end]

    if not candles:
        msg = f"[yellow]캔들 없음: {market} {from_date}~{to_date}. fetch-candles 먼저 실행하세요.[/yellow]"  # noqa: E501
        Console().print(msg)
        return

    df = pd.DataFrame([c.model_dump() for c in windowed_candles])
    warmup_bars = len(windowed_candles) - len(candles)

    # ── --grid: 파라미터 그리드 비교표 모드 ──────────────────────────────────
    if grid_str:
        await _run_grid_output(
            market=market,
            from_date=from_date,
            to_date=to_date,
            strategy_version=strategy_version,
            settings=settings,
            grid_str=grid_str,
            df=df,
        )
        return

    strategy = get_strategy(strategy_version, settings)
    engine = BacktestEngine(strategy=strategy, max_holding_bars=max_hold, warmup_bars=warmup_bars)
    result = engine.run(market, df)

    console = Console()
    table = Table(
        title=f"백테스트 결과 — {market} ({from_date} ~ {to_date})",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("항목", style="dim", min_width=22)
    table.add_column("값", min_width=16)

    table.add_row("전략", strategy_version.upper())
    table.add_row("기간", f"{result.period_from:%Y-%m-%d} ~ {result.period_to:%Y-%m-%d}")
    table.add_row("캔들 수", f"{len(candles):,}")
    table.add_row("거래 횟수", str(len(result.trades)))
    table.add_row("승률", f"{result.win_rate:.1%}")
    table.add_row("평균 수익률", f"{result.avg_pnl_pct:+.2%}")
    table.add_row("누적 수익률", f"{result.cumulative_return_pct:+.2%}")
    table.add_row("MDD", f"{abs(result.mdd_pct):.2%}")
    table.add_row("샤프 (연환산)", f"{result.sharpe_annualized:.2f}")
    table.add_row("평균 보유봉", f"{result.avg_bars_held:.1f}")

    console.print(table)

    if report_path is not None:
        from datetime import datetime as _dt2
        from zoneinfo import ZoneInfo as _ZI

        from signal_program.backtest.report import BacktestReportRenderer

        renderer = BacktestReportRenderer(template_dir=Path("templates"))
        html = renderer.render_html(
            result,
            market=market,
            mode_label=mode_str,
            generated_at=_dt2.now(tz=_ZI("Asia/Seoul")),
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(html, encoding="utf-8")
        typer.echo(f"HTML 리포트 저장: {report_path}")


@app.command()
def walkforward(
    market: Annotated[str, typer.Option("--market", "-m", help="마켓 코드")],
    from_date: Annotated[str, typer.Option("--from", help="시작일 (YYYY-MM-DD)")],
    to_date: Annotated[str, typer.Option("--to", help="종료일 (YYYY-MM-DD)")],
    train_months: Annotated[int, typer.Option("--train-months", help="학습 기간 (개월)")] = 8,
    validate_months: Annotated[int, typer.Option("--validate-months", help="검증 기간 (개월)")] = 2,
    grid: Annotated[
        str, typer.Option("--grid", help="파라미터 그리드 (예: bb_std_mult:1.5,2.0,2.5)")
    ] = "bb_std_mult:1.5,2.0,2.5",
    strategy: Annotated[str, typer.Option("--strategy", help="전략 버전 (v1~v5)")] = "v1",
    report_html: Annotated[str, typer.Option("--report-html", help="HTML 리포트 출력 경로")] = "",
    max_hold: Annotated[
        int,
        typer.Option("--max-hold", help="최대 보유 봉 수 (기본 24)"),
    ] = 24,
) -> None:
    """워크포워드 파라미터 검증 실행. 학습/검증 슬라이딩 윈도우 + 그리드 서치."""
    import asyncio

    report_path = Path(report_html) if report_html else None

    try:
        settings = Settings()
    except SystemExit as exc:
        typer.echo(f"설정 오류: {exc}", err=True)
        raise typer.Exit(1) from exc

    configure_logging(settings)
    asyncio.run(
        _walkforward_async(
            settings,
            market,
            from_date,
            to_date,
            train_months,
            validate_months,
            grid,
            strategy,
            report_path,
            max_hold,
        )
    )


async def _walkforward_async(
    settings: Settings,
    market: str,
    from_date: str,
    to_date: str,
    train_months: int,
    validate_months: int,
    grid_str: str,
    strategy_version: str = "v1",
    report_path: Path | None = None,
    max_hold: int = 24,
) -> None:
    from datetime import datetime as _dt
    from datetime import timedelta as _td
    from zoneinfo import ZoneInfo

    from signal_program.backtest.engine import BacktestEngine
    from signal_program.backtest.report import walkforward_render_html
    from signal_program.backtest.walkforward import (
        WalkforwardEngine,
        parse_grid,
    )
    from signal_program.strategies import get_strategy

    kst = ZoneInfo("Asia/Seoul")
    period_from = _dt.strptime(from_date, "%Y-%m-%d").replace(tzinfo=kst)
    period_to = _dt.strptime(to_date, "%Y-%m-%d").replace(tzinfo=kst) + _td(days=1)

    # V2 전략인데 V1 기본 그리드가 그대로면 V2 기본 그리드로 자동 스왑
    _V1_DEFAULT_GRID = "bb_std_mult:1.5,2.0,2.5"
    _V2_DEFAULT_GRID = "buy_threshold:0.60,0.65,0.70;obv_weight:0.30,0.40,0.50"
    if strategy_version == "v4" and grid_str == _V1_DEFAULT_GRID:
        typer.echo(
            "오류: v4 전략은 V1 기본 그리드(bb_std_mult)를 사용할 수 없습니다.\n"
            "--grid donchian_entry_period:10,20,30,55"
            ";donchian_exit_period:5,10,20 형식으로 지정하세요.",
            err=True,
        )
        raise typer.Exit(1)
    if strategy_version == "v2" and grid_str == _V1_DEFAULT_GRID:
        grid_str = _V2_DEFAULT_GRID
        console = Console()
        console.print(f"[dim]V2 기본 그리드 자동 적용: {_V2_DEFAULT_GRID}[/dim]")
    else:
        console = Console()

    param_grid = parse_grid(grid_str)
    total_months = train_months + validate_months
    console.print(
        f"[cyan]그리드 {len(param_grid)}개 파라미터 조합 × {total_months}개월 윈도우[/cyan]"
    )  # noqa: E501

    base_strategy = get_strategy(strategy_version, settings)
    base_engine = BacktestEngine(strategy=base_strategy, max_holding_bars=max_hold)

    cache_root = Path("data/candles")
    wf_engine = WalkforwardEngine(
        backtest_engine=base_engine,
        candles_cache_root=cache_root,
        param_grid=param_grid,
        strategy_version=strategy_version,
        base_settings=settings,
    )

    wf_result = wf_engine.run(
        market=market,
        period_from=period_from,
        period_to=period_to,
        train_months=train_months,
        validate_months=validate_months,
    )

    # grid_str에서 변화하는 파라미터 키 추출
    # 예: "buy_threshold:0.3;obv_weight:0.1" → ["buy_threshold", "obv_weight"]
    _grid_keys: list[str] = [
        part.split(":")[0].strip() for part in grid_str.split(";") if ":" in part.strip()
    ] or ["bb_std_mult"]
    _param_col_header = _grid_keys[0] if len(_grid_keys) == 1 else "최적 파라미터"

    # 콘솔: fold별 요약
    fold_table = Table(
        title=f"워크포워드 Fold별 결과 — {market}", show_header=True, header_style="bold cyan"
    )
    fold_table.add_column("Fold", min_width=5)
    fold_table.add_column("Validate 기간", min_width=24)
    fold_table.add_column(_param_col_header, min_width=18)
    fold_table.add_column("Train Sharpe", min_width=12)
    fold_table.add_column("Val. Sharpe", min_width=12)
    fold_table.add_column("Val. Cum.", min_width=12)

    for fold in wf_result.folds:
        val_sharpe = fold.validate_result.sharpe_annualized
        val_cum = fold.validate_result.cumulative_return_pct
        if len(_grid_keys) == 1:
            _param_str = str(getattr(fold.best_params, _grid_keys[0], "N/A"))
        else:
            _param_str = ", ".join(f"{k}={getattr(fold.best_params, k, 'N/A')}" for k in _grid_keys)
        fold_table.add_row(
            str(fold.fold_index),
            f"{fold.validate_period_from:%Y-%m-%d} ~ {fold.validate_period_to:%Y-%m-%d}",
            _param_str,
            f"{fold.train_result.sharpe_annualized:.2f}",
            f"[{'green' if val_sharpe >= 0 else 'red'}]{val_sharpe:.2f}[/]",
            f"[{'green' if val_cum >= 0 else 'red'}]{val_cum:+.2%}[/]",
        )

    console.print(fold_table)

    # 콘솔: OOS 합본 요약
    oos = wf_result.out_of_sample_combined
    oos_table = Table(title="Out-of-Sample 합본 결과", show_header=True, header_style="bold green")
    oos_table.add_column("항목", style="dim", min_width=22)
    oos_table.add_column("값", min_width=16)
    oos_table.add_row("거래 횟수 (OOS)", str(len(oos.trades)))
    oos_table.add_row("승률", f"{oos.win_rate:.1%}")
    oos_table.add_row("평균 수익률", f"{oos.avg_pnl_pct:+.2%}")
    oos_table.add_row("누적 수익률 (OOS)", f"{oos.cumulative_return_pct:+.2%}")
    oos_table.add_row("MDD (OOS)", f"{abs(oos.mdd_pct):.2%}")
    oos_table.add_row("샤프 (연환산, OOS)", f"{oos.sharpe_annualized:.2f}")
    oos_table.add_row("평균 보유봉", f"{oos.avg_bars_held:.1f}")
    console.print(oos_table)

    if report_path is not None:
        html = walkforward_render_html(
            wf_result,
            market=market,
            mode_label=f"A,B (grid={grid_str})",
            generated_at=_dt.now(tz=kst),
            template_dir=Path("templates"),
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(html, encoding="utf-8")
        typer.echo(f"HTML 리포트 저장: {report_path}")


# ── backtest --grid: 파라미터 비교표 + JSON 저장 ──────────────────────────────


async def _run_grid_output(
    *,
    market: str,
    from_date: str,
    to_date: str,
    strategy_version: str,
    settings: Settings,
    grid_str: str,
    df: Any,
) -> None:
    """파라미터 그리드 실행 → Rich 비교표 출력 + state/backtest/ JSON 저장."""
    import pandas as pd  # noqa: F401 (df 타입 힌트)

    from signal_program.backtest.grid_search import run_backtest_grid, save_grid_json
    from signal_program.backtest.walkforward import parse_grid

    param_grid = parse_grid(grid_str)
    console = Console()

    console.print(
        f"[bold cyan]파라미터 그리드 실행[/bold cyan] - {market} "
        f"({from_date} ~ {to_date}) / {strategy_version.upper()} / {len(param_grid)}셀"
    )

    cells = run_backtest_grid(
        market=market,
        candles_df=df,
        param_grid=param_grid,
        strategy_version=strategy_version,
        base_settings=settings,
    )

    if not cells:
        console.print("[yellow]그리드 결과 없음[/yellow]")
        return

    # ── Rich 비교표 ──────────────────────────────────────────────────────────
    # 첫 셀의 params 키를 컬럼으로 사용 (동적 파라미터 지원)
    param_keys = list(cells[0].params.keys())

    grid_table = Table(
        title=f"V2 파라미터 그리드 - {market} ({from_date} ~ {to_date})",
        show_header=True,
        header_style="bold cyan",
        show_lines=True,
    )
    grid_table.add_column("셀", min_width=4, justify="right")
    for key in param_keys:
        grid_table.add_column(key, min_width=12, justify="right")
    grid_table.add_column("거래수", min_width=6, justify="right")
    grid_table.add_column("승률", min_width=7, justify="right")
    grid_table.add_column("MDD", min_width=7, justify="right")
    grid_table.add_column("누적수익률", min_width=10, justify="right")
    grid_table.add_column("Sharpe", min_width=7, justify="right")

    for cell in cells:
        r = cell.result
        cum = r.cumulative_return_pct
        sharpe = r.sharpe_annualized
        grid_table.add_row(
            str(cell.cell_index),
            *[f"{cell.params.get(k, 0):.2f}" for k in param_keys],
            str(len(r.trades)),
            f"{r.win_rate:.1%}",
            f"{abs(r.mdd_pct):.2%}",
            f"[{'green' if cum >= 0 else 'red'}]{cum:+.2%}[/]",
            f"[{'green' if sharpe >= 0 else 'red'}]{sharpe:.2f}[/]",
        )

    console.print(grid_table)

    # ── JSON 저장 ─────────────────────────────────────────────────────────────
    json_path = save_grid_json(
        cells=cells,
        market=market,
        period_from=from_date,
        period_to=to_date,
        strategy_version=strategy_version,
        grid_str=grid_str,
        output_dir=Path("state/backtest"),
    )
    console.print(f"[dim]JSON 저장: {json_path}[/dim]")


@app.command(name="fetch-candles")
def fetch_candles(
    market: Annotated[str, typer.Option("--market", "-m", help="마켓 코드")],
    from_date: Annotated[str, typer.Option("--from", help="시작일 (YYYY-MM-DD)")],
    to_date: Annotated[str, typer.Option("--to", help="종료일 (YYYY-MM-DD, 기본: 오늘)")] = "",
) -> None:
    """업비트에서 1시간봉 캔들을 다운로드해 data/candles/ 에 월 단위 parquet으로 저장한다."""
    import asyncio

    asyncio.run(_fetch_candles_async(market, from_date, to_date or None))


@app.command(name="fetch-candles-kr")
def fetch_candles_kr(
    market: Annotated[str, typer.Option("--market", "-m", help="종목코드 (예: 005930)")],
    from_date: Annotated[str, typer.Option("--from", help="시작일 (YYYY-MM-DD)")],
    to_date: Annotated[str, typer.Option("--to", help="종료일 (YYYY-MM-DD, 기본: 오늘)")] = "",
) -> None:
    """KIS에서 국내 주식 일봉(수정주가)을 다운로드해 data/candles/{market}/1440/ 에 저장한다."""
    import asyncio

    try:
        settings = Settings()
    except SystemExit as exc:
        typer.echo(f"설정 오류: {exc}", err=True)
        raise typer.Exit(1) from exc

    if not settings.kis_app_key or not settings.kis_app_secret:
        typer.echo("KIS_APP_KEY / KIS_APP_SECRET 미설정. .env를 확인하세요.", err=True)
        raise typer.Exit(1)

    asyncio.run(
        _fetch_candles_kr_async(
            market,
            from_date,
            to_date or None,
            settings.kis_app_key,
            settings.kis_app_secret,
            settings.kis_is_paper,
        )
    )


async def _fetch_candles_kr_async(
    market: str,
    from_date: str,
    to_date: str | None,
    app_key: str,
    app_secret: str,
    is_paper: bool,
) -> None:
    from datetime import datetime as _dt
    from datetime import timedelta as _td
    from itertools import groupby
    from pathlib import Path
    from zoneinfo import ZoneInfo

    from rich.progress import Progress, SpinnerColumn, TextColumn

    from signal_program.backtest.candles_io import save_candles
    from signal_program.enums import Timeframe
    from signal_program.exchanges.kis_api import KisApiAdapter

    kst = ZoneInfo("Asia/Seoul")
    start = _dt.strptime(from_date, "%Y-%m-%d").replace(tzinfo=kst)
    end = (
        _dt.strptime(to_date, "%Y-%m-%d").replace(tzinfo=kst) + _td(days=1)
        if to_date
        else _dt.now(tz=kst)
    )
    # 요청 캔들 수 = 기간 달력일 + 여유 (영업일은 절반 이하이므로 충분)
    count = int((end - start).total_seconds() / 86400) + 30

    console = Console()

    # VTS 모의투자 서버는 SSL 호스트명 불일치이므로 KisApiAdapter가 verify=False 처리 (ADR-0023).
    async with KisApiAdapter(
        app_key=app_key,
        app_secret=app_secret,
        is_paper=is_paper,
    ) as adapter:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Fetching {market} (일봉)...", total=None)
            all_candles = await adapter.fetch_candles(
                market,
                Timeframe.DAY,
                count=count,
                to=end,
            )
            progress.update(task, description=f"{market}: {len(all_candles)}봉 수신")

    candles = [c for c in all_candles if start <= c.opened_at < end]
    candles.sort(key=lambda c: c.opened_at)

    def _month_key(c: Any) -> str:
        result: str = c.opened_at.strftime("%Y-%m")
        return result

    saved_total = 0
    for month_str, group in groupby(candles, key=_month_key):
        month_list = list(group)
        path = Path(f"data/candles/{market}/1440/{month_str}.parquet")
        save_candles(month_list, path)
        console.print(f"  saved {len(month_list):>4} candles → {path}")
        saved_total += len(month_list)

    end_label = to_date or "오늘"
    console.print(
        f"\n[green]완료[/green] {market}: 총 {saved_total:,}일봉 저장 ({from_date} ~ {end_label})"
    )


async def _fetch_candles_async(market: str, from_date: str, to_date: str | None) -> None:
    import asyncio
    from datetime import datetime as _dt
    from datetime import timedelta as _td
    from itertools import groupby
    from pathlib import Path
    from zoneinfo import ZoneInfo

    import httpx
    from rich.progress import Progress, SpinnerColumn, TextColumn

    from signal_program.backtest.candles_io import save_candles
    from signal_program.enums import Timeframe
    from signal_program.exchanges.upbit import UpbitClient

    kst = ZoneInfo("Asia/Seoul")
    start = _dt.strptime(from_date, "%Y-%m-%d").replace(tzinfo=kst)
    end = (
        _dt.strptime(to_date, "%Y-%m-%d").replace(tzinfo=kst) + _td(days=1)
        if to_date
        else _dt.now(tz=kst)
    )

    console = Console()
    all_candles = []

    async with httpx.AsyncClient(base_url="https://api.upbit.com", timeout=30.0) as http:
        client = UpbitClient(_client=http)
        fetch_to = end

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Fetching {market}...", total=None)

            while True:
                batch = await client.fetch_candles(market, Timeframe.HOUR_1, count=200, to=fetch_to)
                if not batch:
                    break

                all_candles.extend(batch)
                earliest = min(c.opened_at for c in batch)
                desc = f"{market}: {len(all_candles)} 봉 수집 (현재 {earliest:%Y-%m-%d %H:%M})"
                progress.update(task, description=desc)

                if earliest <= start:
                    break

                fetch_to = earliest
                await asyncio.sleep(0.12)  # rate limit 여유

    candles = [c for c in all_candles if start <= c.opened_at < end]
    candles.sort(key=lambda c: c.opened_at)

    def _month_key(c: Any) -> str:
        result: str = c.opened_at.strftime("%Y-%m")
        return result

    saved_total = 0
    for month_str, group in groupby(candles, key=_month_key):
        month_list = list(group)
        path = Path(f"data/candles/{market}/60/{month_str}.parquet")
        save_candles(month_list, path)
        console.print(f"  saved {len(month_list):>4} candles → {path}")
        saved_total += len(month_list)

    end_label = to_date or "오늘"
    console.print(
        f"\n[green]완료[/green] {market}: 총 {saved_total:,} 봉 저장 ({from_date} ~ {end_label})"
    )  # noqa: E501
