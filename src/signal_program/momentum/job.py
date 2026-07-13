"""M2 월간 리밸런스 잡 오케스트레이션 (ADR-0031).

기존 봉단위 RunnerService/KrStockRunnerService와 독립. 월 1회(마지막 거래일 마감 후)
텔레그램 알림을 보내는 것이 전부이며, 자동매매는 하지 않는다(ADR-0002).
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pandas as pd
import structlog

from signal_program.momentum.core import (
    _target_month,
    build_universe,
    diff_portfolio,
    pending_rebalance_asof,
    select_top10,
)

if TYPE_CHECKING:
    from datetime import date

    from signal_program.config import Settings
    from signal_program.notifiers.base import Notifier

log = structlog.get_logger(__name__)

_KST = ZoneInfo("Asia/Seoul")
_REBALANCE_HOUR = 16
_REBALANCE_MINUTE = 30
_DISCLAIMER = "⚠ 정보 제공용 알림입니다. 투자 판단·책임은 본인에게 있습니다."

# 페치 실패 판정 임계치 — 실패 종목 비율이 이 값 이상이면 시스템 장애로 보고 발화 보류(P2-1).
# 정상 운영에서 소수 종목(상폐·거래정지)의 실패는 이 아래라 발화를 막지 않는다.
_FETCH_FAILURE_THRESHOLD = 0.2
# 후보일당 페치 시도 상한 — KIS 장애 시 분당 재시도 폭주 방지(P2-2). 상한 초과 시 당일은
# 더 시도하지 않고, 다음 날 캐치업(pending_rebalance_asof)이 정상 asof로 발화한다.
_MAX_FETCH_ATTEMPTS_PER_DAY = 5


class MomentumJob:
    """유니버스 구성 → top10 선정 → diff → 알림 → 상태 영속화를 조립한다."""

    def __init__(
        self,
        settings: Settings,
        notifier: Notifier,
        *,
        pool_path: Path | None = None,
        candles_root: Path = Path("data/candles"),
        universe_state_path: Path = Path("state/momentum_universe.json"),
        portfolio_state_path: Path = Path("state/momentum_portfolio.json"),
    ) -> None:
        self._settings = settings
        self._notifier = notifier
        self._pool_path = pool_path or Path(settings.momentum_pool_path)
        self._candles_root = candles_root
        self._universe_state_path = universe_state_path
        self._portfolio_state_path = portfolio_state_path
        # 스케줄 상태 (run_forever/_maybe_rebalance 전용, run_once·선정 로직과 무관)
        self._last_rebalanced_asof: date | None = None
        self._loaded_initial_state = False
        self._fetch_attempt_date: date | None = None
        self._fetch_attempts_today = 0

    # ── 종목 풀 ──────────────────────────────────────────────────────────────

    def _load_pool(self) -> list[tuple[str, str]]:
        rows = list(csv.DictReader(self._pool_path.open(encoding="utf-8")))
        return [(r["code"].strip(), r["name"].strip()) for r in rows]

    async def fetch_pool(self) -> bool:
        """종목 풀 일봉 증분 페치. 충분히 성공했으면 True.

        기존 KIS 파이프라인 재사용, 개별 종목 실패는 로그 후 계속하되 성공 여부를
        호출자에게 반환한다 — "페치 실패라 캔들이 없는 것"과 "휴장이라 없는 것"을
        구분하기 위함(P2-1). 판정:
          - 크리덴셜 없음/빈 풀 → False
          - 실패 종목 비율 >= _FETCH_FAILURE_THRESHOLD → False (시스템 장애로 판단)
          - 그 외 → True
        """
        from signal_program.cli import _fetch_candles_kr_async  # 지연 import(순환 방지)

        settings = self._settings
        if not settings.kis_app_key or not settings.kis_app_secret:
            log.warning("momentum_fetch_skipped_no_kis_creds")
            return False

        attempted = 0
        failed = 0
        for code, name in self._load_pool():
            attempted += 1
            try:
                await _fetch_candles_kr_async(
                    code,
                    "2021-01-01",
                    None,
                    settings.kis_app_key,
                    settings.kis_app_secret,
                    settings.kis_is_paper,
                )
            except Exception:
                failed += 1
                log.exception("momentum_fetch_failed", code=code, name=name)

        if attempted == 0:
            log.warning("momentum_fetch_empty_pool")
            return False
        failure_ratio = failed / attempted
        ok = failure_ratio < _FETCH_FAILURE_THRESHOLD
        log.info(
            "momentum_fetch_done",
            attempted=attempted,
            failed=failed,
            failure_ratio=round(failure_ratio, 3),
            fetch_ok=ok,
        )
        return ok

    # ── 가격/거래대금 매트릭스 ───────────────────────────────────────────────

    def load_matrix(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """round2_m2_backtest.load_matrix()와 동일 로직 — 종가/거래대금 매트릭스."""
        codes = [c for c, _ in self._load_pool()]
        closes: dict[str, pd.Series] = {}
        qvs: dict[str, pd.Series] = {}
        for code in codes:
            d = self._candles_root / code / "1440"
            files = sorted(d.glob("*.parquet")) if d.exists() else []
            if not files:
                continue
            df = pd.concat(
                pd.read_parquet(p, columns=["opened_at", "close", "quote_volume"]) for p in files
            )
            df = df.set_index("opened_at").sort_index()
            df = df[~df.index.duplicated(keep="last")]
            closes[code], qvs[code] = df["close"], df["quote_volume"]

        px = pd.DataFrame(closes)
        px.index = pd.DatetimeIndex(px.index).tz_localize(None)
        px = px.sort_index()
        qv = pd.DataFrame(qvs).set_axis(px.index)
        return px, qv

    # ── 유니버스 캐시 ────────────────────────────────────────────────────────

    def get_universe(self, year: int, qv: pd.DataFrame, *, persist: bool = True) -> list[str]:
        cached = self._load_universe_cache()
        if cached is not None and cached.get("year") == year:
            codes: list[str] = cached["codes"]
            return codes

        pool_codes = [c for c, _ in self._load_pool() if c in qv.columns]
        codes = build_universe(qv[pool_codes], year, top_n=self._settings.momentum_universe_size)
        if persist:
            self._save_universe_cache(year, codes)
        return codes

    def _load_universe_cache(self) -> dict | None:  # type: ignore[type-arg]
        if not self._universe_state_path.exists():
            return None
        try:
            data: dict = json.loads(self._universe_state_path.read_text(encoding="utf-8"))  # type: ignore[type-arg]
        except (json.JSONDecodeError, ValueError):
            return None
        return data

    def _save_universe_cache(self, year: int, codes: list[str]) -> None:
        self._universe_state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "year": year,
            "codes": codes,
            "computed_at": datetime.now(_KST).isoformat(),
        }
        self._universe_state_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── 포트폴리오 상태 ──────────────────────────────────────────────────────

    def _load_portfolio(self) -> tuple[list[str], str | None]:
        if not self._portfolio_state_path.exists():
            return [], None
        try:
            data: dict = json.loads(self._portfolio_state_path.read_text(encoding="utf-8"))  # type: ignore[type-arg]
        except (json.JSONDecodeError, ValueError):
            return [], None
        return data.get("codes", []), data.get("asof")

    def _save_portfolio(
        self,
        codes: list[str],
        asof: pd.Timestamp,
        added: list[str] | None = None,
        removed: list[str] | None = None,
    ) -> None:
        self._portfolio_state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "codes": codes,
            "asof": asof.strftime("%Y-%m-%d"),
            "updated_at": datetime.now(_KST).isoformat(),
            "added": added or [],
            "removed": removed or [],
        }
        self._portfolio_state_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── 알림 포맷 ────────────────────────────────────────────────────────────

    def _format_alert(
        self,
        top: pd.DataFrame,
        added: list[str],
        removed: list[str],
        asof: pd.Timestamp,
        name_map: dict[str, str],
    ) -> str:
        month_label = asof.strftime("%Y-%m")
        lines = [f"📊 M2 월간 리밸런스 ({month_label} 마감)", "", "TOP10:"]
        for i, row in enumerate(top.itertuples(index=False), start=1):
            code = str(row.code)
            name = name_map.get(code, code)
            lines.append(
                f"{i}. {name}({code}) — 12-1 모멘텀 {row.momentum:+.1%} / {row.close:,.0f}"
            )
        added_label = ", ".join(f"{name_map.get(c, c)}({c})" for c in added) or "없음"
        removed_label = ", ".join(f"{name_map.get(c, c)}({c})" for c in removed) or "없음"
        lines += [
            "",
            f"⬆ 편입: {added_label}",
            f"⬇ 편출: {removed_label}",
            "",
            f"다음 리밸런스: {_next_month_label(asof)} 마지막 거래일",
            "",
            _DISCLAIMER,
        ]
        return "\n".join(lines)

    # ── 1회 실행 ─────────────────────────────────────────────────────────────

    async def run_once(self, asof: pd.Timestamp, *, dry_run: bool = False) -> dict:  # type: ignore[type-arg]
        """리밸런스 1회 실행. dry_run이면 알림 미발송·상태 미갱신(콘솔/반환값만)."""
        px, qv = self.load_matrix()
        universe = self.get_universe(asof.year, qv, persist=not dry_run)
        top = select_top10(px, universe, asof, n=self._settings.momentum_top_n)

        prev_codes, _ = self._load_portfolio()
        curr_codes = list(top["code"])
        added, removed = diff_portfolio(prev_codes, curr_codes)

        name_map = {c: n for c, n in self._load_pool()}
        text = self._format_alert(top, added, removed, asof, name_map)

        if not dry_run:
            await self._notifier.send_text(text)  # type: ignore[attr-defined]
            self._save_portfolio(curr_codes, asof, added, removed)
            log.info(
                "momentum_rebalance_sent",
                asof=asof.strftime("%Y-%m-%d"),
                top_n=len(curr_codes),
                added=len(added),
                removed=len(removed),
            )

        return {
            "top": top,
            "added": added,
            "removed": removed,
            "text": text,
            "universe_size": len(universe),
        }

    # ── 데일리 스케줄 루프 ───────────────────────────────────────────────────

    async def run_forever(self) -> None:
        """매일(주말 포함) 16:30 KST 이후 체크. 실제 발화 판정은 _maybe_rebalance에 위임."""
        import asyncio

        log.info("momentum_job_started")
        while True:
            try:
                await self._maybe_rebalance(datetime.now(_KST))
            except asyncio.CancelledError:
                raise
            await asyncio.sleep(60)

    def _ensure_initial_state(self) -> None:
        """재기동 시 직전 리밸런스 asof를 1회 로드 — 이미 처리한 달을 재발화하지 않도록."""
        if self._loaded_initial_state:
            return
        _, last_asof = self._load_portfolio()
        self._last_rebalanced_asof = (
            datetime.strptime(last_asof, "%Y-%m-%d").date() if last_asof else None
        )
        self._loaded_initial_state = True

    async def _maybe_rebalance(self, now: datetime) -> None:
        """단일 스케줄 체크(매 분). 발화 스케줄(당월 종료·캐치업) 자체는 건드리지 않고
        그 위에 페치 성공 게이트(P2-1)와 당일 시도 상한(P2-2)만 얹는다.

        - 페치 실패(False) → 오늘 발화 보류, 상태 미갱신. 캐치업(pending_rebalance_asof)이
          다음 성공일에 정상 asof로 발화한다(M19-1 로직이 이미 처리 — 추가 로직 없음).
        - 페치 성공인데 오늘 캔들 없음 → 진짜 휴장 → 최신 관측 캔들로 정상 발화(12/31 케이스).
        - 실패 반복 → 당일 시도 상한으로 분당 재시도 폭주를 막는다.
        """
        self._ensure_initial_state()
        today = now.date()

        in_window = (now.hour, now.minute) >= (_REBALANCE_HOUR, _REBALANCE_MINUTE)
        if not in_window or not _is_rebalance_candidate(today, self._last_rebalanced_asof):
            return

        # 당일 시도 상한 (P2-2)
        if self._fetch_attempt_date != today:
            self._fetch_attempt_date = today
            self._fetch_attempts_today = 0
        if self._fetch_attempts_today >= _MAX_FETCH_ATTEMPTS_PER_DAY:
            return
        self._fetch_attempts_today += 1

        try:
            if not await self.fetch_pool():
                # 페치 실패 → 발화 보류(상태 미갱신). 다음 성공일 캐치업이 정상 asof로 발화.
                log.warning("momentum_fetch_incomplete_defer", check_date=today.isoformat())
                return
            px, _ = self.load_matrix()
            asof = (
                pending_rebalance_asof(
                    pd.DatetimeIndex(px.index), today, self._last_rebalanced_asof
                )
                if not px.empty
                else None
            )
            if asof is not None:
                await self.run_once(asof)
                self._last_rebalanced_asof = asof.date()
        except Exception:
            log.exception("momentum_cycle_failed")


def _next_month_label(asof: pd.Timestamp) -> str:
    nxt = (asof.replace(day=1) + timedelta(days=32)).replace(day=1)
    return nxt.strftime("%Y-%m")


def _is_rebalance_candidate(today: date, last_rebalanced_asof: date | None) -> bool:
    """리밸런스가 밀려 있을 "가능성"만 캘린더로 값싸게 선판정 — 캔들 데이터 불필요.

    fetch_pool()(KIS 150종 페치)을 매일 돌리지 않고 이 값이 True인 후보일에만
    호출하기 위한 게이트. 실제 asof 확정은 pending_rebalance_asof가 담당한다.
    """
    target_year, target_month = _target_month(today)
    if last_rebalanced_asof is None:
        return True
    return (last_rebalanced_asof.year, last_rebalanced_asof.month) != (target_year, target_month)
