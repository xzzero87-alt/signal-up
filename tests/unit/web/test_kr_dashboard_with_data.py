"""kr_dashboard.py — _is_kr_signal 로직 + kr_signals timeframe 필터 커버리지.

lines 21-27 (_is_kr_signal 분기), 57-63 (timeframe 필터) 커버 대상.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import signal_program.web.api.signals as signals_mod
from signal_program.web.api.kr_dashboard import _is_kr_signal
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


@pytest.fixture(autouse=True)
def _reset_signal_history():
    original = signals_mod._signal_history
    yield
    signals_mod._signal_history = original


def _kr_record(code: str = "005930", timeframe: str = "60") -> dict:
    return {
        "signal": {
            "market": code,
            "triggered_at": "2025-01-15T14:00:00+09:00",
            "mode": "D",
            "direction": "buy",
            "strength": "NORMAL",
            "price": 78_000.0,
            "timeframe": timeframe,
            "indicators": {},
        }
    }


def _crypto_record() -> dict:
    return {
        "signal": {
            "market": "KRW-BTC",
            "triggered_at": "2025-01-15T14:00:00+09:00",
            "mode": "A",
            "direction": "buy",
            "strength": "NORMAL",
            "price": 85_000_000.0,
            "indicators": {},
        }
    }


# ── _is_kr_signal ─────────────────────────────────────────────────────────


def test_is_kr_signal_false_for_krw_prefix() -> None:
    assert _is_kr_signal(_crypto_record()) is False


def test_is_kr_signal_true_for_stock_code() -> None:
    assert _is_kr_signal(_kr_record()) is True


def test_is_kr_signal_false_for_non_dict() -> None:
    assert _is_kr_signal("not-a-dict") is False
    assert _is_kr_signal(None) is False


def test_is_kr_signal_false_for_missing_signal_key() -> None:
    assert _is_kr_signal({}) is False


def test_is_kr_signal_false_for_empty_market() -> None:
    assert _is_kr_signal({"signal": {"market": ""}}) is False


def test_is_kr_signal_false_for_non_dict_signal() -> None:
    assert _is_kr_signal({"signal": "not-a-dict"}) is False


# ── kr_signals timeframe 필터 ─────────────────────────────────────────────


def test_kr_signals_timeframe_60_filters_correctly(client: TestClient) -> None:
    mock_hist = MagicMock()
    mock_hist.read_recent.return_value = [
        _kr_record(timeframe="60"),
        _kr_record(timeframe="120"),
        _crypto_record(),
    ]
    signals_mod.set_signal_history(mock_hist)

    resp = client.get("/api/kr/signals?timeframe=60")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["signal"]["timeframe"] == "60"


def test_kr_signals_timeframe_120_filters_correctly(client: TestClient) -> None:
    mock_hist = MagicMock()
    mock_hist.read_recent.return_value = [
        _kr_record(timeframe="60"),
        _kr_record(timeframe="120"),
    ]
    signals_mod.set_signal_history(mock_hist)

    resp = client.get("/api/kr/signals?timeframe=120")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["signal"]["timeframe"] == "120"


def test_kr_signals_no_timeframe_returns_all_kr(client: TestClient) -> None:
    mock_hist = MagicMock()
    mock_hist.read_recent.return_value = [
        _kr_record(timeframe="60"),
        _kr_record(timeframe="120"),
        _crypto_record(),
    ]
    signals_mod.set_signal_history(mock_hist)

    resp = client.get("/api/kr/signals")
    assert resp.status_code == 200
    assert len(resp.json()) == 2  # 코인 1건 제외, 국장 2건


def test_kr_dashboard_filters_kr_signals(client: TestClient) -> None:
    mock_hist = MagicMock()
    mock_hist.read_recent.return_value = [
        _kr_record(),
        _crypto_record(),
    ]
    signals_mod.set_signal_history(mock_hist)

    resp = client.get("/api/kr/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["recent_signals"]) == 1
