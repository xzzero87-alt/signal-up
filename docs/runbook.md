# 운영 플레이북 (Runbook)

> 업비트 시그널 프로그램의 **자가설치 운영자**를 위한 사전 대비 운영 가이드.
> 시나리오별 즉시 조치·진단·영구 해결 절차 + Severity 분류 + 자주 쓰는 명령어를 한곳에 모았다.

**대상 버전:** v1 (M1~M9 라이브 코어). v2 GUI(M13~M16) 완료 후 일부 항목은 GUI 대시보드로 흡수 예정.
**대상 페르소나:** 1인 자가설치 운영자. 외부 알림 채널은 텔레그램 단일(ADR-0003).

---

## 사용 시점

| 시점 | 사용법 |
|------|--------|
| **사전 학습** | 시그널 운영 시작 전 한 번 정독. 시나리오 파악 |
| **장애 발생** | 증상을 확인하고 §3 시나리오 표에서 해당 항목 → 즉시 조치 |
| **사이클 누락·이상** | §3 시나리오 7번부터 점검 |
| **1주/1개월/3개월** | §7 회고 체크리스트로 운영 품질 점검 |
| **postmortem 필요** | §6 템플릿으로 사후 분석 작성 |

---

## 1. Severity 분류

1인 운영 기준 단순화 (PagerDuty급 정밀 분류 X). 자기 자신에게 보내는 신호의 긴급도를 정한다.

| Level | 정의 | 대응 시간 | 예 |
|-------|------|-----------|---|
| **SEV1** | 전체 시그널 송출 중단 | 즉시 (1시간 내) | 텔레그램 인증 실패, 업비트 API 전면 차단, 프로세스 다운 |
| **SEV2** | 일부 기능 저하 (다수 코인 영향) | 24시간 내 | 화이트리스트 절반 fetch 실패, 차트 PNG 생성 일관 실패, signals.jsonl append 일관 실패 |
| **SEV3** | 단일 코인·간헐 이상 | 1주일 내 | 특정 코인 상장폐지, 1~2회 timeout, dry_run 흔적 잔류 |
| **SEV4** | 사소·미관 | 다음 회고 | 메시지 포맷 오타, 로그 가독성, 시각 검증 마이너 흠 |

---

## 2. 즉시 점검 순서 (장애 의심 시)

```
1. uv run signal doctor              # 업비트·텔레그램 ping + 화이트리스트
2. tail -n 50 state/signals.jsonl    # 최근 시그널 이력 (sent_status 확인)
3. 로그 확인 (signal.log 또는 stdout) — cycle_id 기준 grep
4. 현재 시각 vs 다음 평가 시각 — 사이클 트리거 정상인가
5. 텔레그램에 직접 메시지 송신 가능 여부 (수동 curl 테스트)
```

이 5단계로 80%의 SEV1·SEV2 원인이 좁혀진다.

---

## 3. 시나리오별 대응 표

### S1. 텔레그램 알림 전체 누락 (SEV1)

| 항목 | 내용 |
|------|------|
| **증상** | 정시 +2분 이내 메시지 zero, 다수 정시 연속 |
| **즉시** | `uv run signal doctor` — 텔레그램 ping 실패 여부 확인 |
| **진단** | (a) `TELEGRAM_BOT_TOKEN` 유효성 → BotFather에서 토큰 재발급 (b) 봇이 사용자에 의해 차단됨 (c) 텔레그램 API 5xx 일시 다운 |
| **영구** | 토큰 유출 의심 시 BotFather `/revoke`. 자주 차단되면 봇 username 변경 |
| **회고 항목** | postmortem 필수 (사용자 임팩트 큼) |

### S2. 일부 코인만 알림 누락 (SEV2~3)

| 항목 | 내용 |
|------|------|
| **증상** | 특정 코인(예: KRW-LTC)만 누락, 나머지 정상 |
| **즉시** | `tail -n 100 state/signals.jsonl \| grep KRW-LTC` — sent_status 확인 |
| **진단** | (a) 상장폐지 (KRW-LTC 케이스, 2026-05-08 발견) (b) 거래량 필터 미달 (c) 쿨다운 중 (d) fetch_candles 5xx |
| **영구** | 상장폐지면 `.env` WHITELIST_MARKETS에서 제거. 거래량/쿨다운은 정상 동작 |
| **회고 항목** | 화이트리스트 1개월차 회고에서 일괄 점검 |

### S3. 잘못된 시그널 / 알림 과다 (SEV2)

| 항목 | 내용 |
|------|------|
| **증상** | 하루 ≥10개 시그널, 누적 적중률 <30% (백테스트 대비) |
| **즉시** | `signal run --dry-run`으로 전환 (실제 송출 중단, 평가만 계속) |
| **진단** | (a) 임계값 부적절 (CCI ±100이 너무 약함) (b) 시장 상태가 박스권 → 추세 전환 (c) 모드 A/B 동시 트리거가 과다 |
| **영구** | 백테스트(M10~M12)로 임계값 그리드 서치 → CCI ±150 또는 거래량 1.5x로 상향. 운영 1개월차 회고 항목 |
| **회고 항목** | 임계값 변경은 ADR로 기록 (예: ADR-0010 신설 가능) |

### S4. 업비트 API rate limit 위반 (SEV2)

| 항목 | 내용 |
|------|------|
| **증상** | 사이클 timeout, `Remaining-Req` 헤더 0 근접, 429 응답 빈발 |
| **즉시** | `cycle_delay_seconds` 30→60s 증가, `asyncio.Semaphore` 5→3 축소 |
| **진단** | (a) 화이트리스트 너무 큼 (b) IP 차단 (드뭄) (c) 다른 프로세스가 같은 IP 사용 |
| **영구** | 화이트리스트 축소 (19개 → 15개). UpbitClient의 동시성 한도 환경변수로 노출 (v1 외) |
| **회고 항목** | rate limit 위반 발생 빈도 누적 → 1주차 회고 |

### S5. 시스템 재시작 후 첫 사이클 누락 (SEV3)

| 항목 | 내용 |
|------|------|
| **증상** | 13:50에 재시작 → 14:00 정시 시그널 정상, 그러나 직전 13:00 봉의 시그널은 평가 안 됨 |
| **즉시** | `uv run signal scan-once --market KRW-BTC` 등으로 수동 평가 (필요 시 화이트리스트 전체) |
| **진단** | 정상 동작 (라이브 모드는 다음 정시부터). v1 명세대로 |
| **영구** | 부팅 시 직전 봉 1회 자동 평가 옵션은 v1 스코프 외. 필요 시 ADR 신설 후 v2에서 검토 |
| **회고 항목** | 재시작 빈도 추적 |

### S6. 차트 PNG 생성 실패 (SEV3)

| 항목 | 내용 |
|------|------|
| **증상** | 텔레그램에 사진 없이 텍스트만 도착 (sendMessage fallback 작동) |
| **즉시** | 정상 동작 (M8 fallback 보장). 텍스트 메시지로도 매매 판단 가능 |
| **진단** | (a) matplotlib backend 문제 (Agg 강제 누락) (b) `state/charts/` 디스크 부족 (c) 캔들 부족(<80봉) → 평소엔 미발생 |
| **영구** | 디스크 확보 + `cleanup_old_charts` 실행. matplotlib 버전 점검 |
| **회고 항목** | fallback 발생 빈도가 높으면 SEV2로 격상 |

### S7. 디스크 풀 (state/, data/, reports/) (SEV1~2)

| 항목 | 내용 |
|------|------|
| **증상** | cooldown.json 저장 실패(M6 graceful 복구되지만 누적 정보 손실), signals.jsonl append 실패 |
| **즉시** | `python -c "from signal_program.charting.cleanup import cleanup_old_charts; from pathlib import Path; from datetime import timedelta; print(cleanup_old_charts(Path('state/charts'), timedelta(hours=0)))"` — 차트 전체 삭제 |
| **진단** | (a) signals.jsonl 누적 (1년 운영 시 약 50MB 예상) (b) data/candles parquet 누적 (백테스트용) (c) 차트 자동 정리 누락 |
| **영구** | 로그 회전(`logrotate` 또는 직접 스크립트), 차트 정리 주기를 6h로 단축, signals.jsonl 월별 분할 |
| **회고 항목** | 디스크 사용량 모니터링이 부재 — v2 GUI 대시보드에 표시 검토 |

### S8. 무한 루프 정지 (Ctrl+C·kill·OOM) (SEV1~2)

| 항목 | 내용 |
|------|------|
| **증상** | `signal run` 프로세스 다운, 정시 시그널 zero |
| **즉시** | `tmux attach` 또는 systemd `systemctl status` 확인 후 재시작 |
| **진단** | (a) graceful shutdown 흔적(`runner_stopped` 로그) 있음 → 사용자 종료 (b) 없음 → 비정상 종료 (OOM, segfault) |
| **영구** | systemd 또는 supervisor로 자동 재시작 정책. OOM이면 `state/charts` 메모리 누수 점검 |
| **회고 항목** | 비정상 종료 빈도 ≥ 주 1회면 SEV1로 격상 |

### S9. 봉 마감 데이터 지연 (SEV3)

| 항목 | 내용 |
|------|------|
| **증상** | 정시 +30s 호출인데 fetch한 직전봉이 한 봉 전 데이터 |
| **즉시** | `cycle_delay_seconds`를 30→60 또는 90으로 증가 |
| **진단** | (a) 업비트 데이터 반영 지연 (b) 시스템 시계 어긋남 |
| **영구** | `cycle_delay_seconds`를 90s로 영구 변경 권장. NTP 동기 확인 |
| **회고 항목** | 한국 시간대 시장 특성 기록 |

### S10. 텔레그램 토큰 유출 의심 (SEV1)

| 항목 | 내용 |
|------|------|
| **증상** | 봇이 의도하지 않은 메시지 발송, 또는 git 푸시에 토큰 노출 의심 |
| **즉시** | 즉시 BotFather에서 `/revoke` → 새 토큰 발급 → `.env` 갱신 → `signal run` 재시작 |
| **진단** | (a) `.env` 실수 커밋 (`.gitignore` 확인) (b) 로그·응답에 토큰 평문 노출 (c) 외부 노출된 운영 머신 |
| **영구** | `.gitignore` 점검, 로그 마스킹 패턴 검증, M16 보안 가드 회귀 테스트 |
| **회고 항목** | postmortem 필수. ADR로 노출 패턴 기록 |

---

## 4. Escalation 흐름

```
단일 코인 실패     → 로그만, 다음 사이클 자동 재시도          (자동)
사이클 timeout    → logger.error, 다음 사이클 시도          (자동)
N회 연속 사이클 실패 → 운영자 알림 필요 — v1은 수동 점검, v2 GUI 대시보드에서 노출 예정
전체 시그널 다운   → Cowork(여기)로 가져와 분석 + Claude Code에서 fix → 재시작
보안 사고         → 즉시 토큰 revoke + .gitignore 점검 + postmortem 작성
```

v1은 자동 에스컬레이션 채널이 없음(텔레그램 단일). 운영자 본인이 정기 점검하는 게 안전망.

---

## 5. 상태 업데이트 형식 (사용자 본인 메모용)

장기 사고나 회고 시 인용 가치가 있으므로 짧게라도 기록한다. `state/incidents/{date}-{slug}.md` 권장.

```markdown
## Incident: [Title]
**Severity:** SEV[1-4] | **Status:** Investigating | Identified | Monitoring | Resolved
**Last Updated:** YYYY-MM-DD HH:MM KST

### 현재 상황
[지금 무엇이 알려졌는가]

### 조치 사항
- [조치 1]
- [조치 2]

### 다음 단계
- [다음 행동과 예상 시점]

### 타임라인
| 시각 | 이벤트 |
|------|--------|
| HH:MM | [이벤트] |
```

---

## 6. Postmortem 템플릿 (사후 분석)

SEV1·SEV2 또는 학습 가치 있는 사건 발생 시 작성. `docs/postmortems/YYYY-MM-DD-{slug}.md`.

```markdown
## Postmortem: [Title]
**Date:** YYYY-MM-DD | **Duration:** [X시간] | **Severity:** SEV[X]
**Author:** [본인] | **Status:** Draft | Final

### 요약
[2~3문장 평이한 요약]

### 영향
- [영향 받은 사용자/시그널 수]
- [지속 시간]
- [매매 기회 손실 추정 (가능하면)]

### 타임라인
| 시각 (KST) | 이벤트 |
|------------|--------|
| HH:MM | [이벤트] |

### 근본 원인
[무엇이 일으켰는가]

### 5 Whys
1. 왜 [증상]이 발생했나? → [원인 1]
2. 왜 [원인 1]이? → [원인 2]
3. 왜 [원인 2]가? → [원인 3]
4. 왜 [원인 3]이? → [원인 4]
5. 왜 [원인 4]가? → [근본 원인]

### 잘된 점
- [작동한 안전망]

### 부족한 점
- [놓친 부분]

### Action Items
| 항목 | 우선순위 | 마감 |
|------|----------|------|
| [항목] | P0/P1/P2 | YYYY-MM-DD |

### 교훈
[다음에 같은 패턴 발생 시 어떻게 대응할 것인가]

### ADR 신설 필요?
[아키텍처 결정 변경이 필요하면 ADR-NNNN 신설 메모]
```

> **Blameless 원칙**: 본인이 운영자이자 작성자이므로 "내가 실수했다" 대신 "어떤 신호가 빠져 같은 실수 가능했다"로 표현.

---

## 7. 회고 체크리스트

### 7.1 1주차 회고

- [ ] `signal doctor`로 매일 1회 ping 확인했는가
- [ ] `state/signals.jsonl` 누적 수 (사이클당 평균 시그널 수)
- [ ] `sent_status` 분포: ok / failed / cooled_down / dry_run 비율
- [ ] 사이클 timeout 발생 횟수
- [ ] 차트 PNG 생성 실패 횟수
- [ ] 디스크 사용량 변화량
- [ ] 1주 무중단 비율 (G4 목표 ≥95%)

### 7.2 1개월차 회고

- [ ] 시그널 빈도: 코인당 주 1~5회 범위 안인가
- [ ] 라이브 시그널 적중률 (24봉 내 BB 중심선 도달 비율)
- [ ] 백테스트 vs 라이브 일치도
- [ ] 임계값 튜닝 후보 (CCI, 거래량, 쿨다운 시간)
- [ ] 화이트리스트 변동 (상장폐지, 신규 메이저 등장)
- [ ] GUI 사용 만족도 자가 평가 (v2.0 진입 후)
- [ ] ADR 신설/superseded 필요한 결정 누적 점검

### 7.3 3개월차 회고

- [ ] 적중률 ≥50%? (G3 목표)
- [ ] 라이브 MDD ≤25%? (G2 목표, 가상 시뮬)
- [ ] 무인 운영 7일 무중단 ≥95%? (G4)
- [ ] 신규 사용자 온보딩 친화도 ≤30분 검증 (G6, 베타 테스터 1명)
- [ ] v2 → v3(SaaS) 전환 검토 시점 결정
- [ ] PRD/DESIGN/ADR 누적 변경사항 통합 정리

---

## 8. 자주 쓰는 명령어 모음

```bash
# === 라이브 운영 ===
uv run signal serve              # GUI + 데몬 (v2.0)
uv run signal run                # 헤드리스 (v1)
uv run signal run --dry-run      # 텔레그램 송출 없이 평가만

# === 진단 ===
uv run signal doctor             # 업비트·텔레그램·화이트리스트 ping
uv run signal scan-once --market KRW-BTC          # 단발 평가

# === 백테스트 (M10~M12 완료 후) ===
uv run signal backtest --market KRW-BTC --from 2025-01-01 --to 2026-04-30 --mode A,B
uv run signal fetch-candles --market KRW-BTC --from 2025-01-01

# === 로그/상태 점검 ===
tail -f signal.log                                  # 라이브 로그
tail -n 50 state/signals.jsonl                      # 최근 시그널
grep '"sent_status":"failed"' state/signals.jsonl   # 실패 시그널만
grep '"cycle_id":"abc..."' signal.log               # 특정 사이클

# === 정리 ===
python -c "from signal_program.charting.cleanup import cleanup_old_charts; from pathlib import Path; from datetime import timedelta; print(cleanup_old_charts(Path('state/charts'), timedelta(hours=24)))"
ls -lah state/ data/ reports/                       # 디스크 사용량

# === 보안 ===
grep -r "TELEGRAM_BOT_TOKEN" . --exclude-dir=.venv --exclude-dir=.git    # 토큰 노출 점검
git log --all --full-history -- .env                                       # .env 커밋 이력
```

---

## 9. 연관 문서

- [`../PRD.md`](../PRD.md) — Product Requirements
- [`../DESIGN.md`](../DESIGN.md) — 기술 명세서 (운영 §13)
- [`adr/README.md`](adr/README.md) — Architecture Decision Records (ADR-0009 Windows 우회 등)
- [`../README.md`](../README.md) — 설치·시작 가이드
- [`CLAUDE_CODE_PROMPTS.md`](CLAUDE_CODE_PROMPTS.md) — Claude Code 인계 지시문 (구현·디버깅 시점에 활용)

---

> **이 플레이북은 살아있는 문서다.** 새 시나리오 발생 시 §3에 추가, 새 ADR 결정 시 §9에 링크. 1개월차 회고에서 항목 신뢰도 재검토.
