# ADR-0003: 텔레그램 단일 알림 채널

**Date**: 2026-05-07
**Status**: accepted
**Deciders**: 사용자(태민)

## Context

실시간 시그널 전달 채널을 결정해야 한다. 모바일 즉시성, 차트 이미지 첨부 가능성, 구현 단순성, 인증 부담이 핵심 평가 기준이다. v2 확장(`Notifier` Protocol)을 위해 채널 추상화는 유지하되, v1 구현체는 단일 채널로 시작하는 게 KISS에 부합한다.

## Decision

**텔레그램 봇 단일 채널**로 시작한다. `httpx`로 `sendPhoto`/`sendMessage` 엔드포인트를 직접 호출하고, `python-telegram-bot` 라이브러리는 사용하지 않는다(의존성 최소화). 추후 채널 추가는 `Notifier` Protocol을 통해 가능.

## Alternatives Considered

### Alternative 1: Slack
- **Pros**: 워크스페이스 친숙, 차트 이미지 첨부 가능
- **Cons**: 워크스페이스 설정 필요, 봇 토큰 + 채널 ID 두 단계, 모바일 즉시성은 텔레그램보다 약간 떨어짐
- **Why not**: 1인 트레이더 모바일 알림 시나리오에 텔레그램 대비 이점 적음

### Alternative 2: 이메일 (SMTP)
- **Pros**: 가장 보편적
- **Cons**: 모바일 즉시성 낮음, 푸시 알림 신뢰도 낮음, SMTP 자격증명 관리
- **Why not**: 시그널 즉시성이 핵심인데 이메일은 부적합

### Alternative 3: 카카오톡
- **Pros**: 한국 사용자에게 친숙
- **Cons**: 개인 알림용 봇 API 제약(자기 자신에게만 발송 가능 등), OAuth 복잡, 차트 이미지 제약
- **Why not**: 개인 자동 알림에 부적합한 정책 제약

## Consequences

### Positive
- 단일 의존성(`httpx` + 봇 토큰)으로 구현 단순
- iOS/Android 즉시 푸시
- 차트 PNG 첨부가 자연스러움(`sendPhoto`)

### Negative
- 텔레그램 장애 시 fallback 없음 → 시그널 디스크 누적(`state/signals.jsonl`)으로 사후 추적
- 한국 사용자 일부는 텔레그램 미사용 → 사용자 풀 제한

### Risks
- 텔레그램 정책 변경/장애 시 즉시 영향
- **재검토 시점**: 텔레그램 주요 장애 발생 또는 사용자가 다른 채널 요청 시 `Notifier` Protocol 통해 Slack/Discord 추가

## 관련 자료

- [DESIGN.md §5](../../DESIGN.md) — 시그널 송출 정책
- [DESIGN.md §8.4](../../DESIGN.md) — Notifier Protocol
- [PRD.md §5.1.1](../../PRD.md) — R-P0-5
