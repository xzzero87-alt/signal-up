"""설정 파라미터 도움말 텍스트 — M14 툴팁용 정적 dict."""

from __future__ import annotations

SETTING_HELP: dict[str, str] = {
    "bb_period": "볼린저 밴드 계산 기간. 기본 20봉. 짧을수록 신호 잦음.",
    "bb_std_mult": "볼린저 밴드 표준편차 배수. 1.5=더 자주 신호, 2.0=기본, 2.5=보수적.",
    "cci_period": "CCI 계산 기간. 기본 20봉.",
    "cci_threshold_normal": "CCI 일반 신호 임계값. ±100이 기본. 절댓값 클수록 보수적.",
    "cci_threshold_strong": "CCI 강한 신호 임계값. ±200이 기본.",
    "volume_ratio_min_a": "모드 A(평균회귀) 최소 거래량 배수. 기본 1.0배.",
    "volume_ratio_min_b": "모드 B(스퀴즈 돌파) 최소 거래량 배수. 기본 1.5배.",
    "squeeze_lookback": "스퀴즈 판정에 사용할 과거 봉 수. 기본 120봉.",
    "squeeze_quantile": "스퀴즈 판정 분위. 0.20=최근 120봉 중 하위 20% 폭이면 스퀴즈.",
    "cooldown_hours": "같은 (코인, 모드, 방향) 재알림 차단 시간. 기본 2시간.",
    "whitelist_markets": "모니터링할 KRW 마켓 목록. 쉼표로 구분. 예: KRW-BTC,KRW-ETH",
    "telegram_bot_token": "BotFather에서 발급받은 봇 토큰. 비워두면 기존 값 유지.",
    "telegram_chat_id": "알림을 받을 채팅 ID. 본인 사용자 ID 또는 그룹 ID.",
    "dry_run": "켜면 시그널 계산은 하지만 텔레그램 송출은 하지 않음. 테스트용.",
    # 전략 확장 v2.3 (V3 Fractal · V4 Donchian · V5 RSI2)
    "fractal_volume_threshold": "V3 프랙탈 진입 최소 거래량 배수. 기본 1.2배.",
    "fractal_volume_strong": "V3 프랙탈 강한 신호 거래량 배수. 기본 2.0배.",
    "fractal_max_age": "V3 확정 프랙탈 유효 봉 수. 이보다 오래되면 신호 제외. 기본 20봉.",
    "donchian_entry_period": "V4 진입 채널 기간. 직전 N봉 최고가 돌파 시 매수. 기본 20봉.",
    "donchian_exit_period": "V4 청산 채널 기간. 직전 N봉 최저가 이탈 시 매도. 기본 10봉.",
    "donchian_volume_strong": "V4 강한 신호 거래량 배수 (강도 표시 전용). 기본 1.5배.",
    "rsi2_period": "V5 RSI 계산 기간. Connors 기본 2.",
    "rsi2_oversold": "V5 매수 과매도 기준. rsi2가 이 값 미만일 때 매수. 기본 10.",
    "rsi2_overbought": "V5 매도 과매수 기준. rsi2가 이 값 초과일 때 매도. 기본 90.",
    "rsi2_trend_period": "V5 추세필터 SMA 기간. 이 위에서만 매수, 아래에서만 매도. 기본 200봉.",
}
