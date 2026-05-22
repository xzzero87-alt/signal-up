"""typer 기반 CLI 골격.

엔트리포인트: signal
서브커맨드:
    doctor        환경 점검
    run           라이브 루프  [마일스톤 9]
    serve         웹 + 데몬   [마일스톤 13]
    scan-once     단발 평가   [마일스톤 9]
    backtest      백테스트    [마일스톤 10]
    fetch-candles 캔들 다운로드 [마일스톤 10]
"""

from __future__ import annotations

import logging
import os
import sys
from io import TextIOWrapper
from pathlib import Path
from typing import Annotated, Any

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

    async with httpx.AsyncClient(base_url="https://api.upbit.com", timeout=10.0) as http:
        exchange = UpbitClient(_client=http)
        notifier = TelegramNotifier(
            bot_token=SecretStr(settings.telegram_bot_token),
            chat_id=settings.telegram_chat_id,
            dry_run=settings.dry_run,
        )
        runner = RunnerService(
            settings=settings,
            exchange=exchange,
            strategy=strategy,
            cooldown=cooldown,
            notifier=notifier,
            signal_log=signal_log,
            charts_dir=settings.charts_dir,
        )
        import contextlib

        with contextlib.suppress(asyncio.CancelledError):
            await runner.run_forever()


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

    async with httpx.AsyncClient(base_url="https://api.upbit.com", timeout=10.0) as http:
        exchange = UpbitClient(_client=http)
        notifier = TelegramNotifier(
            bot_token=SecretStr(settings.telegram_bot_token),
            chat_id=settings.telegram_chat_id,
            dry_run=settings.dry_run,
        )
        runner = RunnerService(
            settings=settings,
            exchange=exchange,
            strategy=strategy,
            cooldown=cooldown,
            notifier=notifier,
            signal_log=signal_log,
            charts_dir=settings.charts_dir,
        )
        await runner.run_forever()


@app.command(name="scan-once")
def scan_once(
    market: Annotated[str, typer.Option("--market", "-m", help="마켓 코드 (예: KRW-BTC)")],
) -> None:
    """단발성 단일 마켓 즉시 평가. [마일스톤 9에서 구현 예정]"""
    typer.echo("scan-once는 마일스톤 9에서 구현 예정, 현재 사용 불가", err=True)
    raise typer.Exit(1)


@app.command()
def backtest(
    market: Annotated[str, typer.Option("--market", "-m", help="마켓 코드")],
    from_date: Annotated[str, typer.Option("--from", help="시작일 (YYYY-MM-DD)")],
    to_date: Annotated[str, typer.Option("--to", help="종료일 (YYYY-MM-DD)")],
    mode: Annotated[str, typer.Option("--mode", help="전략 모드 (A / B / A,B)")] = "A,B",
    strategy: Annotated[str, typer.Option("--strategy", help="전략 버전 (v1 / v2)")] = "v1",
    report_html: Annotated[
        str,
        typer.Option("--report-html", help="HTML 리포트 출력 경로 (미지정 시 콘솔만)"),
    ] = "",
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
    asyncio.run(_backtest_async(settings, market, from_date, to_date, mode, strategy, report_path))


async def _backtest_async(
    settings: Settings,
    market: str,
    from_date: str,
    to_date: str,
    mode_str: str,
    strategy_version: str = "v1",
    report_path: Path | None = None,
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

    # 월 단위 parquet 로드
    all_candles = []
    cur = start.replace(day=1)
    while cur < end:
        month_str = cur.strftime("%Y-%m")
        path = Path(f"data/candles/{market}/60/{month_str}.parquet")
        if path.exists():
            all_candles.extend(load_candles(path))
        cur = (cur + _td(days=32)).replace(day=1)

    candles = [c for c in all_candles if start <= c.opened_at < end]
    candles.sort(key=lambda c: c.opened_at)

    if not candles:
        msg = f"[yellow]캔들 없음: {market} {from_date}~{to_date}. fetch-candles 먼저 실행하세요.[/yellow]"  # noqa: E501
        Console().print(msg)
        return

    df = pd.DataFrame([c.model_dump() for c in candles])

    strategy = get_strategy(strategy_version, settings)
    engine = BacktestEngine(strategy=strategy)
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
    strategy: Annotated[str, typer.Option("--strategy", help="전략 버전 (v1 / v2)")] = "v1",
    report_html: Annotated[str, typer.Option("--report-html", help="HTML 리포트 출력 경로")] = "",
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
            settings, market, from_date, to_date,
            train_months, validate_months, grid, strategy, report_path
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

    param_grid = parse_grid(grid_str)
    console = Console()
    total_months = train_months + validate_months
    console.print(
        f"[cyan]그리드 {len(param_grid)}개 파라미터 조합 × {total_months}개월 윈도우[/cyan]"
    )  # noqa: E501

    base_strategy = get_strategy(strategy_version, settings)
    base_engine = BacktestEngine(strategy=base_strategy)

    cache_root = Path("data/candles")
    wf_engine = WalkforwardEngine(
        backtest_engine=base_engine,
        candles_cache_root=cache_root,
        param_grid=param_grid,
    )

    wf_result = wf_engine.run(
        market=market,
        period_from=period_from,
        period_to=period_to,
        train_months=train_months,
        validate_months=validate_months,
    )

    # 콘솔: fold별 요약
    fold_table = Table(
        title=f"워크포워드 Fold별 결과 — {market}", show_header=True, header_style="bold cyan"
    )
    fold_table.add_column("Fold", min_width=5)
    fold_table.add_column("Validate 기간", min_width=24)
    fold_table.add_column("최적 bb_std", min_width=10)
    fold_table.add_column("Train Sharpe", min_width=12)
    fold_table.add_column("Val. Sharpe", min_width=12)
    fold_table.add_column("Val. Cum.", min_width=12)

    for fold in wf_result.folds:
        val_sharpe = fold.validate_result.sharpe_annualized
        val_cum = fold.validate_result.cumulative_return_pct
        fold_table.add_row(
            str(fold.fold_index),
            f"{fold.validate_period_from:%Y-%m-%d} ~ {fold.validate_period_to:%Y-%m-%d}",
            str(fold.best_params.bb_std_mult),
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


@app.command(name="fetch-candles")
def fetch_candles(
    market: Annotated[str, typer.Option("--market", "-m", help="마켓 코드")],
    from_date: Annotated[str, typer.Option("--from", help="시작일 (YYYY-MM-DD)")],
    to_date: Annotated[str, typer.Option("--to", help="종료일 (YYYY-MM-DD, 기본: 오늘)")] = "",
) -> None:
    """업비트에서 1시간봉 캔들을 다운로드해 data/candles/ 에 월 단위 parquet으로 저장한다."""
    import asyncio

    asyncio.run(_fetch_candles_async(market, from_date, to_date or None))


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
