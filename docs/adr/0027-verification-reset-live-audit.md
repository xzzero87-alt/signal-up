# ADR-0027: 검증 전면 재평가 — KR 재설계 파킹, v4 피벗 근거 철회, 라이브 코인 전략 실측 의무화

**Date**: 2026-07-09
**Status**: accepted
**Deciders**: xzzero87

## Context

정정 조건(웜업+올바른 max-hold) 전면 재검증 결과: (A) KR 카탈로그 전수(v4·kr_fractal·rsi2·v2)가 게이트 미달 — 최선은 여전히 v1(+19.41% < B&H +23.61%). (B) 코인 피벗 근거였던 "v4 Donchian ETH/XRP B&H 승"은 `should_exit`(ADR-0021) 도입 전 구코드 산물로 확인 — 현재 코드로는 3마켓 전부 절대수익 음수(BTC −51%·ETH −38.7%·XRP −8.9%), 워크포워드 OOS도 전부 음수. (C) 라이브 코인 전략은 게이트로 평가된 적이 없고, 설정 소스 이원화(`run`=.env, `serve`=settings.json 병합) 때문에 **진입점에 따라 v1(BB+CCI) 또는 v3(fractal)로 정체가 갈린다** — settings.json은 `strategy_version=v3`, .env에는 미설정(기본 v1). v3 라이브 채택을 기록한 ADR도 없다.

## Decision

1. **KR 전략 재설계를 무기한 파킹한다.** 카탈로그 전수 미달로 후보가 없다. from-scratch 신규 설계는 라이브 코인 문제 해결 이후에만 재논의.
2. **코인 v4 Donchian 피벗 근거를 철회한다.** v4는 현재 코드 기준 후보 목록에서 제외.
3. **라이브 코인 전략 실측을 의무화한다** (별도 세션): (a) 진입점별 실제 기동 전략을 로그로 실증, (b) v1과 v3 모두 정정 조건으로 게이트 실측 (화이트리스트 마켓, 60분봉, 현재 코드). 결과에 따른 라이브 지위 결정(미달 시 중단 — ADR-0022 규율)은 ADR-0028로.
4. **설정 소스 이원화 수정을 최우선 코드 과제로 격상한다.** "무엇이 라이브인가"를 모호하게 만드는 근본 원인. 실측 완료 직후 착수.

## Alternatives Considered

### Alternative 1: 코인 라이브 즉시 전면 중단
- **Pros**: 규율 최대 일관. 미검증 시그널 노출 즉시 제거.
- **Why not**: 현재 근거 수치가 구코드 측정치라 성급. 실측은 1세션 거리고 알림 전용이라 수일 유지 리스크 제한적. 사용자 결정: 실측 후 판단.

### Alternative 2: 기존 라이브는 소급 예외로 인정
- **Why not**: KR v1을 게이트 미달로 중단(ADR-0026)한 직후라 명백한 자기모순. 기각.

## Consequences

### Positive
- 부정확한 근거(구코드 수치·정체 모호) 위에서 결정하지 않음.
- KR·코인 전체가 동일 규율(게이트 통과 = 라이브 자격)로 수렴.

### Negative
- KR 알림 공백 장기화. 실측 결과에 따라 코인 알림도 중단될 수 있음(제품 전체 알림 0 가능성).

### Risks
- v1·v3 모두 미달 시 라이브 가능 전략이 하나도 없게 됨 — 그 경우 게이트 기준의 제품 적합성(절대 B&H 초과 vs 방어/위험조정)을 **결과와 분리된 회고**로 다룬다(사후 완화가 아니라 프레임 재점검, 별도 ADR).

## 관련 자료

- [ADR-0026](0026-kr-v1-gate-fail-live-stop.md) — KR v1 중단 (동일 규율의 선례)
- [ADR-0022](0022-post-v24-roadmap-edge-first.md) — 게이트 기준
- [ADR-0021](0021-strategy-owned-backtest-exit.md) — should_exit (v4 구코드 경계선)
- [ADR-0017](0017-v2-strategy-no-go-redesign.md) — 현 라이브의 마지막 정성 근거
- `reports/compare/verification_session_2026-07-09_summary.md` — 재검증 세션 전체 결과
