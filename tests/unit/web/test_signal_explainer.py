"""web/signal_explainer.py 단위 테스트."""

from __future__ import annotations

import pytest

from signal_program.web.signal_explainer import _ADVISORY, explain


def _buy(mode: str, ind: dict | None = None) -> dict:
    return {"mode": mode, "direction": "buy", **(ind or {})}


def _sell(mode: str, ind: dict | None = None) -> dict:
    return {"mode": mode, "direction": "sell", **(ind or {})}


# ── V1A MEAN_REVERSION ────────────────────────────────────────────────────────

def test_v1a_buy_summary_contains_buy() -> None:
    r = explain("id", _buy("A"), {"bb_pct_b": -0.05, "cci": -120.0, "volume_ratio": 1.5}, 70)
    assert "매수" in r.summary


def test_v1a_buy_bb_pass_when_at_zero() -> None:
    r = explain("id", _buy("A"), {"bb_pct_b": 0.0, "cci": -120.0, "volume_ratio": 1.5}, 70)
    bb = next(x for x in r.reasons if x.label == "BB %B")
    assert bb.status == "pass"


def test_v1a_buy_cci_pass_when_below_100() -> None:
    r = explain("id", _buy("A"), {"bb_pct_b": -0.05, "cci": -150.0, "volume_ratio": 1.5}, 70)
    cci = next(x for x in r.reasons if "CCI" in x.label)
    assert cci.status == "pass"


def test_v1a_buy_cci_warn_when_above_threshold() -> None:
    r = explain("id", _buy("A"), {"bb_pct_b": -0.05, "cci": -50.0, "volume_ratio": 1.5}, 50)
    cci = next(x for x in r.reasons if "CCI" in x.label)
    assert cci.status == "warn"


def test_v1a_sell_summary_contains_sell() -> None:
    r = explain("id", _sell("A"), {"bb_pct_b": 1.1, "cci": 150.0, "volume_ratio": 1.0}, 60)
    assert "매도" in r.summary


def test_v1a_sell_bb_pass_when_above_1() -> None:
    r = explain("id", _sell("A"), {"bb_pct_b": 1.05, "cci": 150.0, "volume_ratio": 1.0}, 60)
    bb = next(x for x in r.reasons if x.label == "BB %B")
    assert bb.status == "pass"


def test_v1a_returns_3_reasons() -> None:
    r = explain("id", _buy("A"), {}, 50)
    assert len(r.reasons) == 3


# ── V1B SQUEEZE_BREAKOUT ──────────────────────────────────────────────────────

def test_v1b_buy_vol_pass_when_above_1_5() -> None:
    r = explain("id", _buy("B"), {"bb_pct_b": 1.05, "cci": 120.0, "volume_ratio": 1.6}, 70)
    vol = next(x for x in r.reasons if "거래량" in x.label)
    assert vol.status == "pass"


def test_v1b_buy_vol_warn_when_below_1_5() -> None:
    r = explain("id", _buy("B"), {"bb_pct_b": 1.05, "cci": 120.0, "volume_ratio": 1.2}, 60)
    vol = next(x for x in r.reasons if "거래량" in x.label)
    assert vol.status == "warn"


# ── V2 WEIGHTED_SCORE ─────────────────────────────────────────────────────────

def test_v2_buy_contains_score_threshold() -> None:
    r = explain("id", _buy("C"), {"weighted_score": 0.72}, 65)
    assert "0.65" in r.summary


def test_v2_score_pass_when_above_threshold() -> None:
    r = explain("id", _buy("C"), {"weighted_score": 0.72}, 65)
    score_r = next(x for x in r.reasons if "점수" in x.label)
    assert score_r.status == "pass"


def test_v2_score_warn_when_below_threshold() -> None:
    r = explain("id", _buy("C"), {"weighted_score": 0.60}, 50)
    score_r = next(x for x in r.reasons if "점수" in x.label)
    assert score_r.status == "warn"


# ── V3 FRACTAL_BREAKOUT ───────────────────────────────────────────────────────

def test_v3_buy_summary_contains_fractal() -> None:
    r = explain("id", _buy("D"), {"volume_ratio": 1.5, "fractal_age": 10}, 60)
    assert "프랙탈" in r.summary or "Fractal" in r.summary


def test_v3_age_pass_when_le_20() -> None:
    r = explain("id", _buy("D"), {"volume_ratio": 1.5, "fractal_age": 15}, 60)
    age_r = next(x for x in r.reasons if "나이" in x.label)
    assert age_r.status == "pass"


def test_v3_age_warn_when_above_20() -> None:
    r = explain("id", _buy("D"), {"volume_ratio": 1.5, "fractal_age": 25}, 50)
    age_r = next(x for x in r.reasons if "나이" in x.label)
    assert age_r.status == "warn"


# ── V4 DONCHIAN_BREAKOUT ──────────────────────────────────────────────────────

def test_v4_buy_summary_contains_donchian() -> None:
    r = explain("id", _buy("E"), {"volume_ratio": 1.8, "dc_upper": 50000.0}, 65)
    assert "Donchian" in r.summary


def test_v4_vol_pass_when_above_1_5() -> None:
    r = explain("id", _buy("E"), {"volume_ratio": 1.8}, 65)
    vol = next(x for x in r.reasons if "거래량" in x.label)
    assert vol.status == "pass"


# ── V5 RSI2_REVERSION ────────────────────────────────────────────────────────

def test_v5_buy_rsi_pass_when_below_10() -> None:
    r = explain("id", _buy("F"), {"rsi2": 5.0, "volume_ratio": 1.0}, 55)
    rsi = next(x for x in r.reasons if "RSI" in x.label)
    assert rsi.status == "pass"


def test_v5_buy_rsi_warn_when_above_10() -> None:
    r = explain("id", _buy("F"), {"rsi2": 15.0, "volume_ratio": 1.0}, 40)
    rsi = next(x for x in r.reasons if "RSI" in x.label)
    assert rsi.status == "warn"


def test_v5_sell_rsi_pass_when_above_90() -> None:
    r = explain("id", _sell("F"), {"rsi2": 95.0, "volume_ratio": 1.0}, 60)
    rsi = next(x for x in r.reasons if "RSI" in x.label)
    assert rsi.status == "pass"


# ── 공통 ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("mode", ["A", "B", "C", "D", "E", "F"])
def test_advisory_in_all_warnings(mode: str) -> None:
    r = explain("id", {"mode": mode, "direction": "buy"}, {}, 50)
    assert _ADVISORY in r.warnings


def test_unknown_mode_returns_explanation() -> None:
    r = explain("x", {"mode": "Z", "direction": "buy"}, {}, 50)
    assert r.signal_id == "x"
    assert _ADVISORY in r.warnings


def test_signal_id_and_confidence_preserved() -> None:
    r = explain("my_sig_id", _buy("A"), {}, 74)
    assert r.signal_id == "my_sig_id"
    assert r.confidence == 74
