"""TelegramNotifier — DESIGN.md §5.3(메시지 포맷) §5.5(통신 정책).

M7 범위: sendMessage(텍스트)만. sendPhoto(차트) 및 fallback은 M8에서 추가.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import httpx
import structlog

from signal_program.enums import SignalDirection, SignalStrength, StrategyMode

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import SecretStr

    from signal_program.models import Signal

log = structlog.get_logger()

_BASE_URL = "https://api.telegram.org"
_MAX_TEXT_LEN = 4096
_MAX_CAPTION_LEN = 1024

_MODE_LABEL: dict[str, str] = {
    StrategyMode.MEAN_REVERSION.value: "평균회귀",
    StrategyMode.SQUEEZE_BREAKOUT.value: "스퀴즈 돌파",
    StrategyMode.WEIGHTED_SCORE.value: "가중치",  # V2 (ADR-0010)
}

_VERSION_TAG: dict[str, str] = {
    StrategyMode.WEIGHTED_SCORE.value: "[V2]",
}
_EMOJI: dict[tuple[str, str], str] = {
    (SignalDirection.BUY.value, SignalStrength.NORMAL.value): "🟢",
    (SignalDirection.BUY.value, SignalStrength.STRONG.value): "🟢🟢",
    (SignalDirection.SELL.value, SignalStrength.NORMAL.value): "🔴",
    (SignalDirection.SELL.value, SignalStrength.STRONG.value): "🔴🔴",
}

# KR 주식 타임프레임 레이블 (업비트 코인은 "(1h)" 고정)
_TIMEFRAME_KR_LABEL: dict[str, str] = {
    "60": "(60분봉)",
    "120": "(120분봉)",
}


def format_message(signal: Signal) -> str:
    """Signal → 텔레그램 텍스트 변환. 순수 함수(I/O 없음).

    DESIGN.md §5.3 포맷 준수. 4096자 초과 시 말줄임.
    """
    emoji = _EMOJI[(signal.direction.value, signal.strength.value)]
    mode_label = _MODE_LABEL.get(signal.mode.value, signal.mode.value)
    version_tag = _VERSION_TAG.get(signal.mode.value, "[V1]")
    ts_kst = signal.triggered_at.strftime("%Y-%m-%d %H:%M")
    ind = signal.indicators

    # KR 주식(숫자 코드 등)은 타임프레임 레이블, 업비트 코인은 (1h) 고정
    is_kr_stock = not signal.market.startswith("KRW-")
    tf_label = (
        _TIMEFRAME_KR_LABEL.get(signal.timeframe.value, f"({signal.timeframe.value}분봉)")
        if is_kr_stock
        else "(1h)"
    )

    lines = [
        (
            f"{version_tag} {emoji}"
            f" [{signal.direction.value.upper()}-{signal.strength.value.capitalize()}]"
            f" {signal.market} {tf_label} — Mode {signal.mode.value}({mode_label})"
        ),
        f"가격: {signal.price:,.0f} KRW",
        f"BB: 위치 {ind.bb_pct_b:.2f}σ",
        f"CCI(20): {ind.cci:.0f}",
        f"거래량: 평균의 {ind.volume_ratio:.1f}배",
        f"시각: {ts_kst} KST",
    ]

    # V2 전용 지표 줄 (stoch_k / obv 있을 때만 추가)
    if ind.stoch_k is not None:
        lines.append(f"Sto(14,3): K={ind.stoch_k:.1f}%")
    if ind.stoch_d is not None:
        lines.append(f"Sto D: {ind.stoch_d:.1f}%")
    if ind.obv is not None:
        lines.append(f"OBV raw: {ind.obv:+,.0f}")

    lines += [
        "",
        "📊 차트 첨부",
        "ℹ️ 참고용 시그널 — 매매는 직접 판단",
    ]

    text = "\n".join(lines)
    if len(text) > _MAX_TEXT_LEN:
        log.warning("telegram.message_truncated", original_len=len(text))
        text = text[: _MAX_TEXT_LEN - 3] + "..."
    return text


class TelegramNotifier:
    """텔레그램 봇을 통한 시그널 알림 전송.

    DESIGN.md §5.3 메시지 포맷 / §5.5 통신 정책(httpx, 재시도, 마스킹) 준수.
    chart_path 파라미터는 수신만 하고 무시 — TODO(M8): sendPhoto 분기 추가.
    """

    def __init__(
        self,
        bot_token: SecretStr,
        chat_id: str,
        *,
        dry_run: bool = False,
        timeout: float = 10.0,
        max_retries: int = 3,
        http_client: httpx.AsyncClient | None = None,
        _retry_wait_multiplier: float = 1.0,
    ) -> None:
        self._token = bot_token
        self._chat_id = chat_id
        self._dry_run = dry_run
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = http_client
        self._retry_mult = _retry_wait_multiplier

    async def send_signal(self, signal: Signal, chart_path: Path | None = None) -> None:
        """시그널 텔레그램 전송. 실패 시 예외 없이 로깅(§5.5)."""
        if self._dry_run:
            log.info(
                "dry_run_skip_send",
                market=signal.market,
                direction=signal.direction.value,
            )
            return

        if chart_path is not None and chart_path.exists():
            await self._send_photo(chart_path, signal)
        else:
            text = format_message(signal)
            # 토큰은 URL 구성 시에만 꺼냄 — 로그·예외에 절대 출력 금지
            url = f"{_BASE_URL}/bot{self._token.get_secret_value()}/sendMessage"
            payload = {"chat_id": self._chat_id, "text": text}
            await self._send_with_retry(url, payload)

    async def _send_with_retry(self, url: str, payload: dict[str, str]) -> None:
        client = self._client or httpx.AsyncClient()
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await client.post(url, json=payload, timeout=self._timeout)
                if resp.status_code == 200:
                    return
                if 500 <= resp.status_code < 600:
                    log.warning(
                        "telegram.5xx",
                        attempt=attempt,
                        status=resp.status_code,
                        chat_id=self._chat_id,
                    )
                    if attempt < self._max_retries:
                        await asyncio.sleep(self._retry_mult * (2 ** (attempt - 1)))
                    continue
                # 4xx — 재시도 없음
                log.warning(
                    "telegram.client_error",
                    status=resp.status_code,
                    chat_id=self._chat_id,
                )
                return
            except (httpx.NetworkError, httpx.TimeoutException) as exc:
                log.warning(
                    "telegram.network_error",
                    attempt=attempt,
                    exc=type(exc).__name__,
                    chat_id=self._chat_id,
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_mult * (2 ** (attempt - 1)))

        log.error(
            "telegram.send_exhausted",
            max_retries=self._max_retries,
            chat_id=self._chat_id,
        )

    async def _send_photo(self, chart_path: Path, signal: Signal) -> None:
        """sendPhoto (multipart). 실패 시 sendMessage fallback."""
        caption = format_message(signal)
        if len(caption) > _MAX_CAPTION_LEN:
            log.warning("telegram.caption_truncated", original_len=len(caption))
            caption = caption[: _MAX_CAPTION_LEN - 3] + "..."

        url = f"{_BASE_URL}/bot{self._token.get_secret_value()}/sendPhoto"
        photo_bytes = chart_path.read_bytes()
        client = self._client or httpx.AsyncClient()
        success = False

        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await client.post(
                    url,
                    data={"chat_id": self._chat_id, "caption": caption},
                    files={"photo": ("chart.png", photo_bytes, "image/png")},
                    timeout=self._timeout,
                )
                if resp.status_code == 200:
                    success = True
                    return
                if 500 <= resp.status_code < 600:
                    log.warning(
                        "telegram.photo_5xx",
                        attempt=attempt,
                        status=resp.status_code,
                        chat_id=self._chat_id,
                    )
                    if attempt < self._max_retries:
                        await asyncio.sleep(self._retry_mult * (2 ** (attempt - 1)))
                    continue
                break  # 4xx: 재시도 없음
            except (httpx.NetworkError, httpx.TimeoutException) as exc:
                log.warning(
                    "telegram.photo_network_error",
                    attempt=attempt,
                    exc=type(exc).__name__,
                    chat_id=self._chat_id,
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_mult * (2 ** (attempt - 1)))

        if not success:
            log.warning("telegram.sendPhoto_failed_fallback", chat_id=self._chat_id)
            text = format_message(signal)
            msg_url = f"{_BASE_URL}/bot{self._token.get_secret_value()}/sendMessage"
            await self._send_with_retry(msg_url, {"chat_id": self._chat_id, "text": text})
