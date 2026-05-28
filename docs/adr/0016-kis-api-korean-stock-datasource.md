# ADR-0016: KIS Open API (한국투자증권) 국내 주식 데이터 소스 채택

**Date**: 2026-05-21
**Status**: accepted
**Deciders**: 프로젝트 오너

## Context

국내 주식(KOSPI/KOSDAQ) 캔들 데이터를 수집할 소스를 결정해야 한다.
1시간봉(HOUR_1, 60분봉)을 기본 타임프레임으로 사용하며,
2시간봉(HOUR_2, 120분봉) 분석도 지원할 계획이다.
데이터 소스는 무료(또는 저비용), read-only 조회 전용, Python `httpx` 기반 비동기 클라이언트로
구현 가능한 것이어야 한다. 자동매매 기능은 제외(ADR-0002).

## Decision

**한국투자증권 Open API(KIS Open API)**를 국내 주식 캔들 데이터 소스로 채택한다.
`KisApiAdapter`(`exchanges/kis_api.py`)로 구현하며, read-only 캔들 조회만 사용한다.
KIS가 120분봉(HOUR_2)을 미지원하므로, **60분봉 2개를 페어링해 집계**(`_resample_to_120m`)한다.
인증은 OAuth2 액세스 토큰(24h TTL), 만료 10분 전 선제 재발급. Rate limit은 `asyncio.Semaphore(5)`.

## Alternatives Considered

### Alternative 1: 키움증권 OpenAPI+
- **Pros**: 국내에서 가장 널리 사용되는 증권사 API
- **Cons**: Windows COM 기반 → Linux/Mac 미지원; `httpx` 비동기 클라이언트 불가; Docker 배포 불가
- **Why not**: 크로스 플랫폼 Python 프로젝트 원칙에 위배.

### Alternative 2: 유료 데이터 벤더 (FnGuide, Dataguide 등)
- **Pros**: 고품질 데이터, 공시·재무 데이터까지 제공
- **Cons**: 월 수십~수백만 원 구독료; 자가설치 오픈소스 배포에 부적합
- **Why not**: 오픈소스 자가설치 배포(ADR-0006) 원칙과 충돌.

### Alternative 3: FinanceDataReader / pykrx (무료 스크래핑)
- **Pros**: 별도 API 키 불필요
- **Cons**: 공식 API 아님 → 구조 변경 시 파싱 깨짐; 분봉 데이터 미지원 또는 불안정
- **Why not**: 1시간봉 실시간 수집에 필요한 안정성 부족.

## Consequences

### Positive
- 공식 REST API → 안정적이고 문서화된 인터페이스
- 무료 개인 계좌 발급 가능 (실계좌 또는 모의투자 계좌)
- 모의투자(paper) 환경 내장 → `is_paper=True`로 개발·테스트 분리
- `httpx.AsyncClient` 기반 → 업비트 어댑터와 동일 패턴 유지

### Negative
- 사용자가 KIS 계좌와 Open API 앱 키 발급 필요 (추가 온보딩 단계)
- 단일 호출당 최대 30개 캔들 → 150개(5페이지) 수집 시 페이지네이션 필요
- HOUR_2는 집계 방식(`_resample_to_120m`)이므로 KIS 네이티브 120분봉과 미묘한 차이 가능

### Risks
- **KIS API 스펙 변경**: `_parse_candles`의 필드명(`stck_bsop_date` 등) 하드코딩 → 변경 시 파싱 오류. 완화: 파싱 실패 시 WARNING 로그 + 해당 캔들 skip.
- **Rate Limit 초과**: KIS 초당 20건 제한. `asyncio.Semaphore(5)` + `KrStockRunnerService._semaphore(3)` 이중 제한으로 완화.
- **토큰 재발급 실패**: `_ensure_token` 실패 시 `httpx` 예외 전파 → 해당 사이클 전체 실패. 다음 사이클에서 자동 재시도.

## 관련 자료

- [ADR-0015](0015-korean-stock-market-support.md) — 국내 주식 시장 지원 추가 결정
- [ADR-0004](0004-single-1h-timeframe.md) — 1시간봉 단일 타임프레임 (국내 주식은 HOUR_1 + HOUR_2)
- [`exchanges/kis_api.py`](../../src/signal_program/exchanges/kis_api.py) — 구현체
- [KIS Open API 공식 문서](https://apiportal.koreainvestment.com)
