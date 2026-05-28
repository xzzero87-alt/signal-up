# ADR-0015: 국내 주식(KOSPI/KOSDAQ) 시장 지원 추가

**Date**: 2026-05-21
**Status**: accepted
**Deciders**: 프로젝트 오너

## Context

v1~v2.0은 업비트 KRW 마켓(암호화폐)만 지원했다. 동일한 BB+CCI 기술 지표 기반 시그널 로직이
국내 주식 시장(KOSPI/KOSDAQ)에도 적용 가능하다는 판단 아래, 국내 주식 지원 추가를 검토했다.
국내 주식은 암호화폐와 달리 **평일 09:00~15:30 KST**에만 시장이 열리고,
증권사 API(KIS Open API)를 통한 캔들 수집 방식이 다르므로 별도 러너가 필요하다.
Node.js 프로토타입(`korean_stock_signal/`)으로 전체 흐름을 사전 검증한 뒤 Python 메인 프로젝트에 통합했다.

## Decision

국내 주식 시장 지원을 **별도 프로젝트가 아닌 `signal-up`(Python 메인 프로젝트)에 통합**한다.
`KrStockRunnerService`(`kr_runner.py`)를 신설하고 `signal serve` 실행 시
업비트 `RunnerService`와 **asyncio TaskGroup으로 병렬 실행**한다.
시장 개장 시간 외(`_is_market_open` 반환 False)에는 사이클을 건너뛴다.

## Alternatives Considered

### Alternative 1: 별도 독립 프로젝트로 분리
- **Pros**: 암호화폐·주식 코드베이스 완전 분리, 각자 독립 배포 가능
- **Cons**: 설정·텔레그램·쿨다운·차트 등 공통 인프라 중복; 사용자가 두 프로세스 관리 필요
- **Why not**: 공통 `Settings`, `Notifier`, `CooldownStore`, `SignalLog` 재사용이 훨씬 효율적. Node.js 프로토타입은 검증용으로만 사용하고 Python으로 통합.

### Alternative 2: Node.js 프로토타입을 그대로 운영
- **Pros**: 이미 동작하는 코드, 빠른 배포
- **Cons**: Python 메인 프로젝트와 런타임·의존성·배포 방식 이원화; 장기 유지 비용 증가
- **Why not**: 사용자가 `uv run signal serve` 한 줄로 암호화폐·국내 주식을 동시에 돌리는 UX를 원함.

### Alternative 3: 실시간 WebSocket 기반 시세 수신
- **Pros**: 봉 마감 즉시 처리 가능
- **Cons**: KIS WebSocket API 별도 인증·재연결 관리 필요; 복잡도 대폭 증가
- **Why not**: 1시간봉 기준 평가이므로 정각 폴링으로 충분. v2 후보.

## Consequences

### Positive
- `signal serve` 하나로 업비트·국내 주식 동시 운영
- 텔레그램·쿨다운·차트·설정 등 공통 인프라 완전 재사용
- 국내 주식 설정(`kr_whitelist_symbols`, `kr_cycle_delay_seconds`)을 GUI 설정 페이지에서 동일하게 관리 가능

### Negative
- `signal serve` 프로세스가 두 루프를 동시에 실행하므로 CPU/메모리 사용량 증가
- 국내 주식 장 외 시간에도 프로세스가 살아있어야 함 (sleep 대기)

### Risks
- **국내 주식 오류가 업비트 루프에 영향**: asyncio TaskGroup 분리로 완화. 각 루프 독립 에러 처리.
- **KIS API 인증 만료**: `KisApiAdapter._ensure_token()`이 만료 10분 전 선제 재발급으로 완화.
- **시장 공휴일 미처리**: `_is_market_open`은 평일/시간만 체크, 공휴일 미지원 → v2 개선 항목.

## 관련 자료

- [ADR-0016](0016-kis-api-korean-stock-datasource.md) — KIS API 데이터 소스 채택
- [ADR-0002](0002-no-autotrading.md) — 자동매매 제외 (국내 주식도 동일 원칙 적용)
- [PRD.md §5.3](../../PRD.md) — 국장 관련 Non-Goals
