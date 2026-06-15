"""signals.py — set_signal_history 주입 + 실데이터 경로 커버리지 테스트.

lines 29, 42-45, 57-100 커버 대상:
- set_signal_history
- recent_signals(with data)
- signal_cards(with data)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import signal_program.web.api.signals as signals_mod
from signal_program.web.app import create_app


@pytest.fixture()
def client(tmp_path):  # type: ignore[no-untyped-def]
    app = create_app(
        settings_path=tmp_path / "settings.json",
        reports_dir=tmp_path / "reports",
        candles_cache_root=tmp_path / "candles",
    )
    with TestClient(app) as c:
        yield c


def _crypto_record(
    market: str = "KRW-BTC",
    direction: str = "buy",
    strength: str = "NORMAL",
) -> dict:
    return {
        "signal": {
            "market": market,
            "triggered_at": "2025-01-15T14:00:00+09:00",
            "mode": "A",
            "direction": direction,
            "strength": strength,
            "price": 85_000_000.0,
            "indicators": {
                "bb_pct_b": 0.85,
                "cci": 120.5,
                "volume_ratio": 2.1,
            },
        }
    }


@pytest.fixture(autouse=True)
def _reset_signal_history():
    """각 테스트 전후로 global 상태 초기화."""
    original = signals_mod._signal_history
    yield
    signals_mod._signal_history = original


# ── set_signal_history ────────────────────────────────────────────────────


def test_set_signal_history_injects_instance() -> None:
    mock = MagicMock()
    signals_mod.set_signal_history(mock)
    assert signals_mod._signal_history is mock


# ── recent_signals with data ──────────────────────────────────────────────


def test_recent_signals_returns_records_when_history_set(client: TestClient) -> None:
    record = _crypto_record()
    mock_hist = MagicMock()
    mock_hist.read_recent.return_value = [record]
    signals_mod.set_signal_history(mock_hist)

    resp = client.get("/api/signals/recent")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_recent_signals_passes_filters_to_history(client: TestClient) -> None:
    mock_hist = MagicMock()
    mock_hist.read_recent.return_value = []
    signals_mod.set_signal_history(mock_hist)

    client.get("/api/signals/recent?market=KRW-BTC&direction=buy&limit=10")
    kw = mock_hist.read_recent.call_args.kwargs
    assert kw["market"] == "KRW-BTC"
    assert kw["direction"] == "buy"
    assert kw["limit"] == 10


# ── signal_cards with data ────────────────────────────────────────────────


def test_signal_cards_returns_entries_when_history_set(client: TestClient) -> None:
    mock_hist = MagicMock()
    mock_hist.read_recent.return_value = [_crypto_record()]
    signals_mod.set_signal_history(mock_hist)

    resp = client.get("/api/signals/cards")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["market"] == "KRW-BTC"
    assert data[0]["direction"] == "buy"


def test_signal_cards_strong_signal(client: TestClient) -> None:
    mock_hist = MagicMock()
    mock_hist.read_recent.return_value = [_crypto_record(strength="STRONG")]
    signals_mod.set_signal_history(mock_hist)

    resp = client.get("/api/signals/cards")
    assert resp.status_code == 200
    assert resp.json()[0]["strength"] == "STRONG"


def test_signal_cards_skips_invalid_triggered_at(client: TestClient) -> None:
    bad_record = {
        "signal": {
            "market": "KRW-ETH",
            "triggered_at": "not-a-date",
            "mode": "A",
            "direction": "sell",
            "strength": "NORMAL",
            "price": 1_000_000.0,
            "indicators": {},
        }
    }
    mock_hist = MagicMock()
    mock_hist.read_recent.return_value = [bad_record]
    signals_mod.set_signal_history(mock_hist)

    resp = client.get("/api/signals/cards")
    assert resp.status_code == 200
    assert resp.json() == []


def test_signal_cards_returns_empty_when_no_history(client: TestClient) -> None:
    signals_mod._signal_history = None
    resp = client.get("/api/signals/cards")
    assert resp.status_code == 200
    assert resp.json() == []


def test_signal_cards_sparkline_prices_mixed_records(client: TestClient) -> None:
    """sparkline_prices 있는 레코드와 없는 레코드가 혼재해도 올바르게 변환된다."""
    with_prices = {
        "signal": {
            "market": "KRW-BTC",
            "triggered_at": "2025-01-15T14:00:00+09:00",
            "mode": "A",
            "direction": "buy",
            "strength": "NORMAL",
            "price": 85_000_000.0,
            "indicators": {"bb_pct_b": 0.85, "cci": 120.5, "volume_ratio": 2.1},
        },
        "sparkline_prices": [100.0, 200.0, 300.0],
    }
    without_prices = _crypto_record(market="KRW-ETH")

    mock_hist = MagicMock()
    mock_hist.read_recent.return_value = [with_prices, without_prices]
    signals_mod.set_signal_history(mock_hist)

    resp = client.get("/api/signals/cards")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["sparkline_prices"] == [100.0, 200.0, 300.0]
    assert data[1]["sparkline_prices"] is None
