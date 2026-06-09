"""국장 큐레이션 유니버스 — v2.2 §4 시작목록 (43종).

출처: handoff/v2.2_settings_ia_redesign.md §4. 설정 ①종목설정 국장 탭의 멀티셀렉트 소스.
``GET /api/markets/kr`` 가 이 목록을 ``[{code, name, market, sector}]`` 로 반환한다.

## 교차검증 완료 (2026-06, 작업 #2·#3)

시장이전 정책(작업 #3): **현재 시장만 기록(option-a)**.
  과거 이력은 코드·커밋 메시지에 남기고, 필드 값은 현재 상장 시장만 반영한다.
  이력 보존이 필요해지면 ADR을 추가하고 모델 스키마를 변경한다.

코드·종목명 검증: 43종 모두 핸드오프 제공값과 동일. 상장폐지·코드변경 없음.

시장 분류:
  KOSDAQ(7종): 에코프로비엠·에코프로·HLB·펄어비스·카카오게임즈·에스엠·JYP Ent.
  KOSPI(36종): 나머지 전부.
    - 셀트리온(068270): 2018 KOSPI 이전 — KOSPI 확정.
    - 알테오젠(196170): 2026-06 KOSDAQ→KOSPI 이전 — KOSPI 확정 (option-a 적용).

섹터 주의:
  - 고려아연(010130)·POSCO홀딩스(005490): KRX 공식 업종(비철금속·철강)이나
    소재 대분류로 '화학·소재' 채택. 섹터는 필터용 레이블이므로 의도적 단순화.
"""

from __future__ import annotations

from typing import NamedTuple

from signal_program.enums import KrMarket


class KrStock(NamedTuple):
    """큐레이션 종목 1건 (정적). web 계층 비의존 — enums만 참조."""

    code: str
    name: str
    market: KrMarket
    sector: str


_KOSPI = KrMarket.KOSPI
_KOSDAQ = KrMarket.KOSDAQ

KR_UNIVERSE: tuple[KrStock, ...] = (
    # 반도체
    KrStock("005930", "삼성전자", _KOSPI, "반도체"),
    KrStock("000660", "SK하이닉스", _KOSPI, "반도체"),
    # IT·전자
    KrStock("009150", "삼성전기", _KOSPI, "IT·전자"),
    KrStock("018260", "삼성에스디에스", _KOSPI, "IT·전자"),
    KrStock("066570", "LG전자", _KOSPI, "IT·전자"),
    # 2차전지
    KrStock("373220", "LG에너지솔루션", _KOSPI, "2차전지"),
    KrStock("006400", "삼성SDI", _KOSPI, "2차전지"),
    KrStock("247540", "에코프로비엠", _KOSDAQ, "2차전지"),
    KrStock("086520", "에코프로", _KOSDAQ, "2차전지"),
    # 화학·소재
    KrStock("051910", "LG화학", _KOSPI, "화학·소재"),
    KrStock("010130", "고려아연", _KOSPI, "화학·소재"),
    KrStock("005490", "POSCO홀딩스", _KOSPI, "화학·소재"),
    # 인터넷
    KrStock("035420", "NAVER", _KOSPI, "인터넷"),
    KrStock("035720", "카카오", _KOSPI, "인터넷"),
    # 게임
    KrStock("259960", "크래프톤", _KOSPI, "게임"),
    KrStock("036570", "엔씨소프트", _KOSPI, "게임"),
    KrStock("251270", "넷마블", _KOSPI, "게임"),
    KrStock("263750", "펄어비스", _KOSDAQ, "게임"),
    KrStock("293490", "카카오게임즈", _KOSDAQ, "게임"),
    # 엔터
    KrStock("041510", "에스엠", _KOSDAQ, "엔터"),
    KrStock("035900", "JYP", _KOSDAQ, "엔터"),
    # 자동차
    KrStock("005380", "현대차", _KOSPI, "자동차"),
    KrStock("000270", "기아", _KOSPI, "자동차"),
    KrStock("012330", "현대모비스", _KOSPI, "자동차"),
    # 바이오
    KrStock("207940", "삼성바이오로직스", _KOSPI, "바이오"),
    KrStock("068270", "셀트리온", _KOSPI, "바이오"),
    KrStock("196170", "알테오젠", _KOSPI, "바이오"),
    KrStock("028300", "HLB", _KOSDAQ, "바이오"),
    # 금융
    KrStock("105560", "KB금융", _KOSPI, "금융"),
    KrStock("055550", "신한지주", _KOSPI, "금융"),
    KrStock("086790", "하나금융지주", _KOSPI, "금융"),
    KrStock("032830", "삼성생명", _KOSPI, "금융"),
    KrStock("000810", "삼성화재", _KOSPI, "금융"),
    # 지주·상사
    KrStock("028260", "삼성물산", _KOSPI, "지주·상사"),
    KrStock("003550", "LG", _KOSPI, "지주·상사"),
    KrStock("034730", "SK", _KOSPI, "지주·상사"),
    # 통신
    KrStock("017670", "SK텔레콤", _KOSPI, "통신"),
    KrStock("030200", "KT", _KOSPI, "통신"),
    # 에너지·유틸
    KrStock("015760", "한국전력", _KOSPI, "에너지·유틸"),
    KrStock("096770", "SK이노베이션", _KOSPI, "에너지·유틸"),
    KrStock("010950", "S-Oil", _KOSPI, "에너지·유틸"),
    # 운송
    KrStock("011200", "HMM", _KOSPI, "운송"),
    # 소비재
    KrStock("090430", "아모레퍼시픽", _KOSPI, "소비재"),
)
