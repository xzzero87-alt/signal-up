# 마일스톤 20 — 코인 돈치안 추세추종 알림 [ADR-0032 1단계]

## 전제 (필수 선행)

- **M19-3 P0(`coin_enabled` 게이트 + 러너 조립 단순화) 먼저.** 현재 데몬을 켜면 NO-GO 판정된 코인 v1 러너가 무조건 기동한다(cli.py). M20은 별도 러너·별도 플래그로 추가하고, 죽은 v1이 되살아나지 않음을 테스트로 단언할 것.
- 설정 소스 분열 버그 잔존: `donchian_enabled`는 `.env`와 `state/settings.json` **양쪽** 설정.

## 설정

- `donchian_enabled: bool = False`
- `donchian_daily_summary: bool = True`

## 전략 상수 (설정 노출 금지 — ADR-0032 동결, 코드 상수)

- `DONCHIAN_UNIVERSE` = KRW-BTC ETH XRP SOL TRX DOGE XLM LINK ADA BCH SUI HBAR AVAX CRO SHIB NEAR DOT UNI PEPE APT (20종)
- ENTRY_CH=20, EXIT_CH=10, RSI_N=14, RSI_TH=50, MACD=(12,26,9), TRAIL=-15%

## 파일

- `strategies/donchian_trend.py` — 마감 일봉 기준 시그널 산출 (순수 함수)
- `jobs/donchian_job.py` — 스케줄·상태·알림 (M19 momentum job 패턴)
- `state/donchian_state.json` — 가상 포지션 `{market: {entry_date, entry_price, peak}}`

## 로직

- **Upbit 일봉 경계 = KST 09:00** (UTC 0시). 매일 **09:10 KST** 스캔, 대상 = 직전 마감 일봉. 진행 중 봉 제외(하우스 룰).
- 페치: 20종 × 최소 60봉. 실패율 ≥20% → 발화 보류 + 다음 성공일 캐치업 (M19-2 `fetch_pool() -> bool` 패턴 재사용).
- 진입: `close > max(high[-20:], 당일 제외)` AND `RSI14 > 50` AND `MACD(12,26) > 0` → 포지션 오픈 기록.
- 청산: `close < min(low[-10:], 당일 제외)` OR `close/peak - 1 <= -0.15` → 클로즈 기록. `peak`는 보유 중 close 최고가.
- 알림(텔레그램): 진입/청산 발생 즉시. `daily_summary=true`면 **매일 09:10 요약 1줄 무조건 발송**(보유 N종·신규·청산·변동 없음) — 구동 헬스체크 겸용.
- KST aware datetime, 토큰 마스킹.

## 테스트 (필수)

1. **백테스트-라이브 거래 대조** (M19 교훈): 8년 일봉으로 job 로직 오프라인 시뮬 → `reports/compare/round6/` 확정 세트 재현과 진입일·청산일 목록 완전 일치.
2. 경계 단위 테스트: 돌파 당일 중복 진입 금지, 트레일링·채널 청산 동시 발생 처리, 상장 초기 워밍업 미달 종목 스킵.
3. 페치 실패 보류·캐치업.
4. `donchian_enabled=true`여도 코인 v1 러너 미기동 단언 (M19-3 회귀).
5. 알림 페이로드 스냅샷.

## 금지

- 파라미터·유니버스 설정화 금지, 자동매매 금지(ADR-0002), momentum job·기존 v1 코드 수정 금지(M19-3 제외).

## 산출물

변경 요약 + 대조 테스트 결과 → Cowork Evaluator 검증 후 `donchian_enabled=true` 점화.
