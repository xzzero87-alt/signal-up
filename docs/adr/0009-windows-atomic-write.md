# ADR-0009: Windows에서 atomic write 우회 (플랫폼 분기)

**Date**: 2026-05-12
**Status**: accepted
**Deciders**: 사용자(태민) + 마일스톤 6 구현 발견

## Context

M6(CooldownStore) 구현 중 `state/cooldown.json` 저장에 표준 atomic write 패턴 — 임시 파일에 쓰고 `os.replace`로 단일 단계 교체 — 을 적용했다. Unix 계열에서는 안정 동작했으나 Windows에서 **AV(Anti-Virus) 스캐너가 임시 파일을 잠근 상태에서 `os.replace`가 PermissionError**를 던지는 현상이 반복 발견되었다. AV 종류·설정에 따라 빈도가 다르고 결정적으로 회피할 방법이 없다.

## Decision

플랫폼 분기로 처리한다.
- **Unix (Linux/macOS)**: 기존 atomic write 유지 — UUID 기반 임시 파일에 쓰고 `os.replace`로 교체
- **Windows**: 직접 쓰기 — 임시 파일 없이 대상 파일에 바로 `open(..., "w") + write`
- 동시 쓰기 안전성은 양쪽 모두 `threading.Lock`으로 보장 (M6 구현 그대로)

## Alternatives Considered

### Alternative 1: 모든 플랫폼에서 직접 쓰기
- **Pros**: 코드 단순, 플랫폼 분기 불필요
- **Cons**: Unix에서 atomic 보장 손실, 부분 쓰기 위험
- **Why not**: Unix는 atomic write가 표준이고 추가 비용 없음. 일부러 약하게 갈 이유 없음

### Alternative 2: 모든 플랫폼에서 atomic write 시도 + 재시도
- **Pros**: 코드 단일, atomic 정신 유지
- **Cons**: Windows에서 AV 충돌 시 재시도해도 잠금 풀릴 때까지 불확실. 사이클 지연
- **Why not**: 재시도 비용 ↑, 보장 ↓. 운영 가시성도 떨어짐

### Alternative 3: 외부 라이브러리(`atomicwrites`, `safer` 등)
- **Pros**: 검증된 라이브러리, 플랫폼 차이 추상화
- **Cons**: 의존성 추가, `atomicwrites`는 유지보수 정체 상태(2022 이후 커밋 없음), `safer`는 비교적 신생
- **Why not**: 의존성 추가 비용 > 우리가 직접 분기하는 비용. KISS 원칙

### Alternative 4: SQLite로 전환
- **Pros**: ACID 트랜잭션 보장, atomic write 고민 불필요
- **Cons**: state/cooldown 한 가지에만 SQLite를 도입하면 일관성 깨짐. JSON 정책(ADR-0008)과 충돌
- **Why not**: ADR-0008과 모순. SQLite 도입은 별도 ADR 필요

## Consequences

### Positive
- Windows·Unix 모두에서 신뢰성 있게 동작
- 외부 의존성 추가 없음
- 동시성은 `threading.Lock`으로 양쪽 모두 보장 (race 방지)
- ADR-0008의 JSON 단일 source of truth 정책 그대로 유지

### Negative
- Windows에서 부분 쓰기 위험 (open + write 중 프로세스 강제 종료 시 파일 손상)
  → 완화: M6의 graceful recovery(`_load_from_disk` 손상 시 빈 dict 반환)가 안전망. 사이클 1회 누락이지 영구 손실 아님
- 코드 내 `platform.system()` 분기 추가 — 테스트도 양쪽 분기 모두 검증해야 함
- Windows에서 `state/cooldown.json`이 잠시 비어 보이는 순간 발생 가능 (open ~ write 사이) → 외부 도구로 동시 읽기 시 문제 가능, 그러나 GUI(M14)는 같은 프로세스 내라 영향 없음

### Risks
- Windows AV 정책이 바뀌어 직접 쓰기마저 잠금 → 그때는 SQLite 전환 검토(별도 ADR)
- `state/settings.json`(M14 GUI 저장)에도 같은 문제 발생 시 동일 패턴 적용. 코드 중복 발생하면 공용 헬퍼(`state/atomic.py`)로 추출 권장
- **재검토 시점**: M14(설정 페이지) 구현 시 같은 패턴이 두 번째로 등장하면 헬퍼 추출. 그 시점에 본 ADR을 superseded 처리할지 결정

## 구현 메모

```python
# state/cooldown.py 패턴 예시 (M6 구현 인용)
import platform
from pathlib import Path
from threading import Lock

_lock = Lock()
_IS_WINDOWS = platform.system() == "Windows"

def _save_to_disk(path: Path, data: dict) -> None:
    with _lock:
        if _IS_WINDOWS:
            # 직접 쓰기 — AV 잠금 회피
            path.write_text(json.dumps(data), encoding="utf-8")
        else:
            # UUID tmp + atomic replace
            tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.replace(tmp, path)
            if not _IS_WINDOWS:  # 권한 600 (Unix만)
                os.chmod(path, 0o600)
```

## 관련 자료

- [ADR-0008](0008-settings-storage.md) — `state/settings.json` 단일 source of truth (같은 디렉토리·같은 패턴)
- [DESIGN.md §5.2](../../DESIGN.md) — 쿨다운 영속 정책
- 발견 시점: M6 구현 중(2026-05-12), 커밋 919ba84 / e7d7b48
