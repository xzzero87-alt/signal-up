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
    # 전략 V2 (4지표 가중치, ADR-0010)
    "bb_weight": "V2 BB 가중치. 4지표 합이 1.00 권장. 기본 0.20.",
    "cci_weight": "V2 CCI 가중치. 4지표 합이 1.00 권장. 기본 0.20.",
    "sto_weight": "V2 Stochastic 가중치. 4지표 합이 1.00 권장. 기본 0.20.",
    "obv_weight": "V2 OBV 가중치. 거래량 중시 기본 0.40 (ADR-0010 §2). 합이 1.00 권장.",
    "buy_threshold": "V2 매수 점수 임계값. 지표 가중 합이 이 값 이상 시 매수 신호. 기본 0.65.",
    "sell_threshold": "V2 매도 점수 임계값. 지표 가중 합이 이 값 이상 시 매도 신호. 기본 0.65.",
    "sto_oversold": "V2 Stochastic 과매도 기준. 이 값 미만 시 매수 점수 가산. 기본 15.",
    "sto_overbought": "V2 Stochastic 과매수 기준. 이 값 초과 시 매도 점수 가산. 기본 85.",
    # 전략 확장 v2.3 (V3 Fractal · V4 Donchian · V5 RSI2)
    "fractal_lookback": "V3 프랙탈 판정 좌우 봉 수. Williams Fractal N봉 기준. 기본 100봉.",
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
    # 국장 전략 (ADR-0018)
    "kr_strategy": (
        "국장 시그널 전략. 프랙탈=국장 전용(ADR-0018),"
        " 코인 전략 공유=위에서 선택한 코인 전략을 국장에도 적용."
    ),
    # AI enrichment (ADR-0020)
    "ai_enrichment_enabled": (
        "시그널 발송 후 AI가 최근 뉴스 요약을 후속 메시지로 첨부합니다 (ADR-0020)."
        " 매수·매도 판단 아님, 정보 제공 목적. Anthropic API 키 필수."
    ),
    "anthropic_api_key": (
        "Anthropic Console에서 발급받은 API 키 (sk-ant-...). 비워두면 기존 값 유지."
    ),
    "ai_enrichment_model": (
        "사용할 Claude 모델 ID. 기본 claude-haiku-4-5. 변경 시 비용 구조 달라짐."
    ),
    "ai_enrichment_daily_cap": "하루 최대 AI 보강 호출 수 (1~500). 기본 30. KST 자정 리셋.",
    "ai_enrichment_timeout_seconds": (
        "Anthropic API 호출 타임아웃 (초). 5~120. 기본 25. 초과 시 조용히 무시."
    ),
}
