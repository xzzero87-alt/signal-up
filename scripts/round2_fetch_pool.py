"""Round 2 — 후보 풀(~145종) KIS 일봉 수집 (ADR-0029 Decision 2, 2안: KIS 하이브리드).

scripts/round2_pool.csv의 종목을 기존 KIS 파이프라인으로 페치해 data/candles/에 캐시한다.
이미 캐시된 종목(core43 등)은 스킵. 상장폐지 등 실패 종목은 기록 후 계속.

실행:
    uv run python scripts/round2_fetch_pool.py

산출:
    data/candles/{code}/1440/*.parquet   — 표준 캐시 (기존 포맷 동일)
    reports/compare/round2/fetch_log.csv — 종목별 성공/실패/스킵
"""
from __future__ import annotations

import asyncio
import csv
from pathlib import Path

from signal_program.cli import _fetch_candles_kr_async
from signal_program.config import Settings

POOL = Path("scripts/round2_pool.csv")
CACHE = Path("data/candles")
OUT = Path("reports/compare/round2")
FROM_DATE = "2021-01-01"


async def main() -> None:
    settings = Settings()
    if not settings.kis_app_key or not settings.kis_app_secret:
        raise SystemExit("KIS_APP_KEY / KIS_APP_SECRET 미설정 (.env 확인)")

    OUT.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(POOL.open(encoding="utf-8")))
    log: list[dict[str, str]] = []

    for i, row in enumerate(rows, 1):
        code, name = row["code"].strip(), row["name"].strip()
        dest = CACHE / code / "1440"
        if dest.exists() and any(dest.glob("*.parquet")):
            log.append({"code": code, "name": name, "status": "skip_cached"})
            continue
        try:
            await _fetch_candles_kr_async(
                code, FROM_DATE, None,
                settings.kis_app_key, settings.kis_app_secret, settings.kis_is_paper,
            )
            n = len(list(dest.glob("*.parquet"))) if dest.exists() else 0
            log.append({"code": code, "name": name,
                        "status": "ok" if n else "empty"})
            print(f"[{i}/{len(rows)}] {code} {name}: {'OK' if n else '데이터 없음'}")
        except Exception as exc:  # noqa: BLE001 — 리서치 수집: 실패 기록 후 계속
            log.append({"code": code, "name": name, "status": f"fail: {exc}"})
            print(f"[{i}/{len(rows)}] {code} {name}: 실패 — {exc}")
        await asyncio.sleep(0.3)

    with (OUT / "fetch_log.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["code", "name", "status"])
        w.writeheader()
        w.writerows(log)
    ok = sum(1 for r in log if r["status"] == "ok")
    skip = sum(1 for r in log if r["status"] == "skip_cached")
    print(f"[완료] 신규 {ok} / 스킵 {skip} / 실패·없음 {len(log) - ok - skip}")


if __name__ == "__main__":
    asyncio.run(main())
