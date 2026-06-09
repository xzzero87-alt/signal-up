"""GET /api/signals/{signal_id}/explanation 엔드포인트 통합 테스트."""

from __future__ import annotations

import urllib.parse
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import signal_program.web.api.signals as signals_mod
from signal_program.web.app import create_app

_TRIGGERED_AT = "2025-01-15T14:00:00+09:00"
_MARKET = "KRW-BTC"
_SIGNAL_ID = f"{_TRIGGERED_AT}_{_MARKET}"


@pytest.fixture()
def client(tmp_path):  # type: ignore[no-untyped-def]
    app = create_app(
        settings_path=tmp_path / "settings.json",
        reports_dir=tmp_path / "reports",
        candles_cache_root=tmp_path / "candles",
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_signal_history():
    original = signals_mod._signal_history
    yield
    signals_mod._signal_history = original


def _mock_history(records: list) -> object:
    mock = MagicMock()
    mock.read_recent.return_value = records
    return mock


def _record(
    mode: str = "A",
    direction: str = "buy",
    strength: str = "NORMAL",
    indicators: dict | None = None,
) -> dict:
    return {
        "signal": {
            "market": _MARKET,
            "triggered_at": _TRIGGERED_AT,
            "mode": mode,
            "direction": direction,
            "strength": strength,
            "price": 85_000_000.0,
            "indicators": indicators or {
                "bb_pct_b": -0.05,
                "cci": -120.0,
                "volume_ratio": 1.5,
            },
        }
    }


def _url(signal_id: str) -> str:
    return "/api/signals/" + urllib.parse.quote(signal_id, safe="") + "/explanation"


# ── 404 ───────────────────────────────────────────────────────────────────────

def test_404_when_no_history(client) -> None:  # type: ignore[no-untyped-def]
    signals_mod._signal_history = None
    assert client.get(_url(_SIGNAL_ID)).status_code == 404


def test_404_when_signal_not_found(client) -> None:  # type: ignore[no-untyped-def]
    signals_mod._signal_history = _mock_history([_record()])
    assert client.get(_url("nonexistent_id")).status_code == 404


# ── 200 ───────────────────────────────────────────────────────────────────────

def test_200_when_signal_found(client) -> None:  # type: ignore[no-untyped-def]
    signals_mod._signal_history = _mock_history([_record()])
    resp = client.get(_url(_SIGNAL_ID))
    assert resp.status_code == 200


def test_response_has_required_fields(client) -> None:  # type: ignore[no-untyped-def]
    signals_mod._signal_history = _mock_history([_record()])
    data = client.get(_url(_SIGNAL_ID)).json()
    assert "signal_id" in data
    assert "confidence" in data
    assert "summary" in data
    assert "reasons" in data
    assert "warnings" in data


def test_signal_id_matches_request(client) -> None:  # type: ignore[no-untyped-def]
    signals_mod._signal_history = _mock_history([_record()])
    data = client.get(_url(_SIGNAL_ID)).json()
    assert data["signal_id"] == _SIGNAL_ID


def test_v1a_buy_has_3_reasons(client) -> None:  # type: ignore[no-untyped-def]
    signals_mod._signal_history = _mock_history([_record(mode="A", direction="buy")])
    data = client.get(_url(_SIGNAL_ID)).json()
    assert len(data["reasons"]) == 3


def test_confidence_is_in_range(client) -> None:  # type: ignore[no-untyped-def]
    signals_mod._signal_history = _mock_history([_record()])
    data = client.get(_url(_SIGNAL_ID)).json()
    assert 0 <= data["confidence"] <= 100


def test_reasons_have_status_field(client) -> None:  # type: ignore[no-untyped-def]
    signals_mod._signal_history = _mock_history([_record()])
    data = client.get(_url(_SIGNAL_ID)).json()
    for reason in data["reasons"]:
        assert reason["status"] in ("pass", "warn", "neutral")
