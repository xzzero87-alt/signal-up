"""integration 테스트 공통 픽스처."""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    return f"tests/integration/cassettes/{request.module.__name__.split('.')[-1]}"


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, str]:
    return {"record_mode": "new_episodes"}
