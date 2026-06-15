# Claude Code 지시문 — v2.4.0 릴리스 (CHANGELOG 절단 + 태그 + 푸시)

> **작성:** 2026-06-12 Cowork 설계 세션 · **갱신:** 2026-06-15 (워킹 트리 실제 상태 반영)
> **선행 조건:** walkforward v4 세션 완료 (be67dcd, 99290e3까지 커밋됨).
> **현재 워킹 트리 (2026-06-15 확인 — 예상 상태):** 깨끗하지 않다. 아래 3개만 있으면 정상이고 그대로 진행한다:
>   - `M CHANGELOG.md` — **2.4.0 절단이 이미 미커밋으로 적용돼 있음** (HEAD엔 `[Unreleased]`만, 워킹 트리가 `## [2.4.0] — 2026-06-12` 헤더 삽입 + 누락 항목 3건 추가). 이미 올바른 최종 형태.
>   - `?? docs/prompts/release-v2.4.0-prompt.md`, `?? docs/prompts/sparkline-realdata-prompt.md` — 미추적 문서 2건.
>   위 3개 **외의** staged/unstaged 변경이 있으면 중단하고 보고. (특히 `src/` 변경이 끼어 있으면 즉시 중단.)
> **목적:** origin 대비 ~20커밋 미푸시 상태 해소 + Unreleased 비대화 정리. **코드 변경 없음** —
> 이 세션은 문서·태그·푸시만 한다.
> **선행 숙지:** `CLAUDE.md` 변경 금지 영역.

---

## 사전 점검

1. `git status -s` — 위 "현재 워킹 트리" 3개 항목과 일치하는지 확인. 불일치(특히 `src/` 변경)면 중단·보고.
   `.git/index.lock`이 남아 있는데 (2026-06-15 기준 존재 확인됨) 실행 중인 git 프로세스가 없으면 해당 lock 파일만 삭제.
2. `git log --oneline v2.3.0..HEAD` — 이번 릴리스에 포함될 커밋 범위 = **v2.3.0 이후 전체 ~57커밋**.
   (origin 대비 미푸시는 ahead 20 — 둘은 다른 수치다. 릴리스는 v2.3.0 이후 전체를 담는다.)

## Task 1 — CHANGELOG 정합 검증 (절단은 이미 워킹 트리에 적용됨)

> 2.4.0 절단은 이미 워킹 트리에 미커밋으로 들어와 있다. **다시 이동/절단하지 말 것.** 검증만 한다.

1. `git diff CHANGELOG.md`로 미커밋 변경을 확인 — `## [2.4.0] — 2026-06-12` 헤더가 빈 `## [Unreleased]`
   바로 아래 삽입돼 있고, 모든 v2.4 항목이 2.4.0 아래에 있는지 본다.
2. `git log v2.3.0..HEAD`의 feat/fix 커밋과 2.4.0 항목을 대조. 누락된 사용자 가시 변경이 있으면 보완
   (walkforward v4 그리드 확장 + `--max-hold` CLI 옵션 — 커밋 9617d9c, be67dcd — 포함 여부 확인).
3. 형식은 Keep a Changelog 유지 (추가/변경/수정). `[Unreleased]`는 빈 헤더로 남긴다.

## Task 2 — 품질 게이트 (코드 수정 금지)

```bash
uv run ruff check src/
uv run ruff format --check src/
uv run mypy src/
uv run pytest --cov=src/ -m "" --cov-fail-under=70
uv run pip-audit
```

**실패 시 고치지 말고 실패 내용을 보고하고 중단.** (게이트 수리는 별도 세션 — 이 세션 범위 아님.)

## Task 3 — 커밋 + 태그 + 푸시

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): v2.4.0 절단"
git tag v2.4.0
git push origin master --tags
```

## 보고만 하고 건드리지 말 것

- `pyproject.toml`의 `version = "0.1.0"` — 태그 이력(v2.0.x~v2.3.0)과 어긋난 드리프트.
  기존 릴리스들도 bump하지 않았으므로 **이번에도 변경 금지**, 세션 종료 보고에 한 줄 언급만.
- 테스트/커버리지 경고, deprecation 경고 — 기록만.

## 범위 제한 (하지 말 것)

- src/ 코드 변경 일절 금지
- 버전 번호 체계 변경, pyproject version bump
- Unreleased에 없는 항목의 소급 작성 (커밋에 근거 없는 항목 금지)

## 완료 기준

- [ ] CHANGELOG에 `[2.4.0] — 2026-06-12` 섹션 + 빈 Unreleased
- [ ] 게이트 5종 모두 초록 (실패 시 중단·보고였는지 명시)
- [ ] `git push origin master --tags` 성공, `git status -sb`에 ahead 0 확인
- [ ] 커밋 1개 (CHANGELOG 절단)

## 세션 시작 명령

```powershell
cd C:\Users\user3\Desktop\VibeCoding\signal-up
claude "docs/prompts/release-v2.4.0-prompt.md 를 읽고 그대로 수행해줘"
```
