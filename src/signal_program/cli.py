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
from typing import Annotated, Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from signal_program.config import Settings
from signal_program.logging_config import configure_logging

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

    async with httpx.AsyncClient(timeout=10.0) as http:
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
    port: Annotated[int, typer.Option("--port", help="웹 서버 포트")] = 8765,
    bind: Annotated[str, typer.Option("--bind", help="바인드 주소")] = "127.0.0.1",
) -> None:
    """웹 대시보드 + 백그라운드 데몬 실행. [마일스톤 13에서 구현 예정]"""
    raise NotImplementedError("마일스톤 13에서 구현")


@app.command(name="scan-once")
def scan_once(
    market: Annotated[str, typer.Option("--market", "-m", help="마켓 코드 (예: KRW-BTC)")],
) -> None:
    """단발성 단일 마켓 즉시 평가. [마일스톤 9에서 구현 예정]"""
    raise NotImplementedError("마일스톤 9에서 구현")


@app.command()
def backtest(
    market: Annotated[str, typer.Option("--market", "-m", help="마켓 코드")],
    from_date: Annotated[str, typer.Option("--from", help="시작일 (YYYY-MM-DD)")],
    to_date: Annotated[str, typer.Option("--to", help="종료일 (YYYY-MM-DD)")],
    mode: Annotated[str, typer.Option("--mode", help="전략 모드 (A / B / A,B)")] = "A,B",
) -> None:
    """저장된 parquet 캔들로 백테스트를 실행하고 결과를 표로 출력한다."""
    import asyncio

    try:
        settings = Settings()
    except SystemExit as exc:
        typer.echo(f"설정 오류: {exc}", err=True)
        raise typer.Exit(1) from exc

    configure_logging(settings)
    asyncio.run(_backtest_async(settings, market, from_date, to_date, mode))


async def _backtest_async(
    settings: Settings,
    market: str,
    from_date: str,
    to_date: str,
    mode_str: str,
) -> None:
    from datetime import datetime as _dt
    from datetime import timedelta as _td
    from pathlib import Path
    from zoneinfo import ZoneInfo

    import pandas as pd

    from signal_program.backtest.candles_io import load_candles
    from signal_program.backtest.engine import BacktestEngine
    from signal_program.strategies.bb_cci import BbCciStrategy

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


@app.command(name="fetch-candles")
def fetch_candles(
    market: Annotated[str, typer.Option("--market", "-m", help="마켓 코드")],
    from_date: Annotated[str, typer.Option("--from", help="시작일 (YYYY-MM-DD)")],
    to_date: Annotated[
        str, typer.Option("--to", help="종료일 (YYYY-MM-DD, 기본: 오늘)")
    ] = "",
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
                batch = await client.fetch_candles(
                    market, Timeframe.HOUR_1, count=200, to=fetch_to
                )
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
    console.print(f"\n[green]완료[/green] {market}: 총 {saved_total:,} 봉 저장 ({from_date} ~ {end_label})")  # noqa: E501
