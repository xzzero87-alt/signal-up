# ADR-0020: AI 시그널 컨텍스트 보강 (Claude API 이벤트 드리븐 호출)

**Date**: 2026-06-10
**Status**: accepted
**Deciders**: 프로젝트 오너

## Context

시그널 알림은 "언제"는 답하지만 "지금 무슨 상황에서 온 시그널인지"(뉴스·체제)는 답하지 못한다.
실시간 AI 감시는 비용·안정성에서 데몬보다 열등하므로, 실시간성은 기존 데몬이 유지하고
**시그널 발생 이벤트 시에만** Claude API를 호출해 짧은 컨텍스트 요약을 텔레그램에 후속
메시지로 첨부한다. ADR-0002(자동매매 금지)와 정합: 판단·권유가 아닌 정보 첨부만 한다.

## Decision

1. **호출 시점**: 코인 시그널이 실제 발송된 직후(`dry_run` 시 호출 안 함), 시그널당 1회.
2. **비차단 후속 메시지 패턴**: 기존 시그널 발송 경로는 무변경. 발송 성공 후
   `asyncio.create_task`로 enrichment를 fire-and-forget 실행. 실패·타임아웃은 삼키고
   로그만 남긴다 — **enrichment가 시그널을 지연·차단하는 일은 절대 없다**.
3. **HTTP 클라이언트**: anthropic SDK를 추가하지 않고 기존 `httpx`로
   `POST /v1/messages` 직접 호출 (의존성 추가 회피, CLAUDE.md 의존성 규칙).
   web_search server tool 사용(max_uses≤2)으로 최근 뉴스를 근거로 포함.
4. **가드레일**: 일일 호출 상한(기본 30, KST 자정 리셋), 타임아웃(기본 25초),
   응답은 "사실 요약·출처 도메인 표기·매수/매도 권유 금지" 시스템 프롬프트로 고정.
   메시지 끝에 "정보 제공 목적, 투자 판단 아님" 고정 문구.
5. **설정**: `ai_enrichment_enabled`(기본 **false**), `anthropic_api_key`(시크릿 —
   로그·뷰 마스킹), `ai_enrichment_model`(기본 `claude-haiku-4-5`),
   `ai_enrichment_daily_cap`, `ai_enrichment_timeout_seconds`.
   **GUI 노출은 같은 릴리스에 포함** (FINDING-3 교훈: GUI 미노출 설정은 화면 간 모순을 만든다).
6. **Notifier Protocol 불변**: §8.4 `send_signal` 시그니처는 손대지 않는다.
   `TelegramNotifier`에 Protocol 외 공개 메서드 `send_text(text: str)`를 추가하고,
   enrichment 서비스는 콜백(`Callable[[str], Awaitable[None]]`)으로 주입받는다.

## Consequences

- (+) 폰에서 시그널과 함께 "왜 지금인지" 맥락 확인. 호출당 비용 ~수십 원 이하(Haiku), 상한으로 캡.
- (+) 데몬 안정성 영향 없음 (격리 실패, 비차단).
- (−) Anthropic API 키 보유 필요. 외부 의존(API 장애 시 enrichment만 조용히 생략).
- (−) LLM 요약의 부정확 가능성 → 고정 면책 문구 + 출처 도메인 표기로 완화.
- 국장(KIS) 시그널 경로는 본 ADR 범위 외 — 코인 경로 검증 후 후속 결정.

## Alternatives considered

- **anthropic SDK 추가**: 편하지만 의존성 1개 추가 대비 이득 없음 (단순 POST 1개). 기각.
- **상시 AI 감시 루프**: 비용·비결정성·중복(데몬이 이미 실시간 담당). 기각.
- **시그널 메시지 본문에 인라인 합성**: 시그널 발송이 API 지연에 묶임. 기각 (후속 메시지 채택).
- **OpenRouter 무료 모델** (2026-06-10 검토): 모델 토큰은 무료(일 50회, $10 충전 시 1,000회)지만
  핵심 가치인 웹 검색은 검색당 $0.005 유료라 총비용 차이 미미(시그널당 ~14원 vs ~20원).
  피크 스로틀링·실패 호출 한도 차감 등 안정성 열위로 기각. 비용이 문제가 되면 재검토.
