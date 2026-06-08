# 개발 루프 — Planner → Generator → Evaluator

> 이 프로젝트의 표준 개발 진행 구조. 한 작업을 **계획 → 구현 → 평가** 3단계 루프로 돌린다.
> 결정 근거: [ADR-0019](adr/0019-planner-generator-evaluator-loop.md).
> UI 작업의 세부 역할 분담은 [`ui/agent-roles.md`](ui/agent-roles.md)가 이 가이드의 Generator/Evaluator 하위로 들어간다.

## 한눈에

```
요구 ─▶ [Planner] ─ spec ─▶ [Generator] ─ diff ─▶ [Evaluator] ─┐
            ▲                                                    │
            └──────────── 임계 미달 시 반송 (피드백) ◀───────────┘
                          임계 통과 시 ─▶ 커밋
```

각 단계는 권한이 다르다. **Planner·Evaluator는 읽기 전용**, Generator만 쓰기.

## 단계별 정의

### 1. Planner (읽기 전용)

- **입력**: 사용자 요구 한 줄 / 이슈.
- **산출**: 작업분해 + 성공기준 + 제약(하드라인) 명시. 필요 시 PRD·DESIGN·task_list·ADR 갱신.
- **도구**: `planner` 에이전트 · `/plan` · `gan-planner`.
- **반드시 박아둘 제약** (CLAUDE.md 변경 금지 영역):
  - 자동매매·주문 코드 금지 (ADR-0002)
  - DESIGN.md §8.1~8.5 도메인 시그니처 동결 (필드 추가만 허용)
  - 진행 중(미마감) 봉 사용 금지, 모든 평가는 봉 마감 close 기준
  - KST timezone-aware, 시크릿 마스킹
- **출력 형식**: `목표 → 단계 → 각 단계 verify 기준` (CLAUDE.md §4 Goal-Driven).

### 2. Generator (쓰기)

- **입력**: Planner의 spec + Evaluator 피드백(반송 시).
- **산출**: 코드 변경. TDD 등급 작업은 RED→GREEN→REFACTOR, 커밋도 그 단위로 분리.
- **도구**: `gan-generator` · `tdd-guide`. UI는 `ui/agent-roles.md`의 토큰·CSS / 템플릿 역할로 세분.
- **금지**: spec 밖 기능 추가(YAGNI), 인접 코드 임의 개선, 기존 시그니처 수정.

### 3. Evaluator (읽기 전용)

- **입력**: Generator의 diff.
- **산출**: PASS / FAIL + 실패 시 위치·원인 피드백 (수정은 하지 않고 Generator로 반송).
- **도구**: `gan-evaluator` · `code-reviewer` · `scripts/ui_check.py`.
- **합격 기준 (게이트 4종 = 채점 루브릭)**:

  ```bash
  uv run ruff check src/ --fix && uv run ruff format src/
  uv run mypy src/                          # strict
  uv run pytest --cov=src/ --cov-fail-under=70
  uv run python scripts/ui_check.py         # UI 변경 시
  ```

  전부 통과해야 커밋. 하나라도 실패하면 Generator로 반송.

## 바로 쓰는 루프 도구

| 도구 | 용도 |
|------|------|
| `/gan-build` | Generator↔Evaluator 빌드 루프 (전략·로직·백엔드). 점수 임계까지 반복 |
| `/gan-design` | 위 루프의 프론트엔드/시각 작업 버전 (UI 재설계) |
| `/santa-loop` | 독립 리뷰어 2명이 둘 다 승인해야 머지하는 적대적 이중검증 (안전 민감 변경) |

## 병렬 실행 규칙

- 읽기 전용 단계(Planner·Evaluator)는 무엇과도 병렬 가능.
- Generator 내부 병렬은 **겹치지 않는 파일**만 (예: `app.css` ∥ `*.html`).
- 같은 파일 동시 편집 금지 → 순차. 세부 표는 [`ui/agent-roles.md`](ui/agent-roles.md) §파일 충돌 규칙.

## 비용 주의

에이전트는 매 호출마다 콜드스타트로 컨텍스트를 재구성한다. 루프 반복·다중 에이전트는 비용이 빠르게 누적되므로, 작업 규모에 맞춰 라운드 수에 상한을 둔다.

## 표준 진행 예시

"V6 전략 추가" 요청 →

1. **Planner**: DESIGN §3 명세화 + ADR 초안 + task_list (지표→모델→전략→등록→UI), 하드라인 명시.
2. **Generator**: 지표 RED→GREEN, 전략 RED→GREEN, 등록·설정·UI. 커밋 단위 분리.
3. **Evaluator**: 게이트 4종 + 백테스트 1회. FAIL이면 위치·원인만 보고 → 2로 반송.
4. PASS → 커밋·푸시.
