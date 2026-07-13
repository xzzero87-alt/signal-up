"""pytest 공통 픽스처 (마일스톤 1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import structlog

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _reset_structlog_after_test() -> Iterator[None]:
    """각 테스트 후 structlog을 라이브러리 기본값으로 리셋 — xdist 워커 크래시 방지.

    configure_logging()(또는 이를 호출하는 serve/run 진입 함수)은 structlog을
    PrintLoggerFactory(sys.stdout) + cache_logger_on_first_use=True로 전역 구성한다. 테스트가
    이를 실행하면 워커의 structlog 로거가 그 테스트의 pytest-xdist 캡처 stdout에 캐시·고정되고,
    teardown으로 stdout이 닫힌 뒤 같은 워커의 다른 테스트가 로그를 쓰면
    'ValueError: I/O operation on closed file'로 워커가 죽어 테스트가 연쇄 미실행된다.
    reset_defaults()는 cache_logger_on_first_use=False로 되돌려 매 호출 시 현재 stdout에 새로
    바인딩되게 하므로 닫힌-파일 참조가 남지 않는다.
    """
    yield
    structlog.reset_defaults()
