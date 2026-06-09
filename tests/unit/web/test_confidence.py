"""web/confidence.py 단위 테스트."""

from __future__ import annotations

from signal_program.web.confidence import score_confidence


def test_base_score_is_50() -> None:
    assert score_confidence(strength="normal", mode="A", volume_ratio=None, cci=None, bb_pct_b=None, bad_rate=0.0) == 50


def test_strong_adds_15() -> None:
    assert score_confidence(strength="STRONG", mode="A", volume_ratio=None, cci=None, bb_pct_b=None, bad_rate=0.0) == 65


def test_strong_case_insensitive() -> None:
    assert score_confidence(strength="strong", mode="A", volume_ratio=None, cci=None, bb_pct_b=None, bad_rate=0.0) == 65


def test_volume_2x_adds_20() -> None:
    assert score_confidence(strength="normal", mode="A", volume_ratio=2.0, cci=None, bb_pct_b=None, bad_rate=0.0) == 70


def test_volume_1_5x_adds_10() -> None:
    assert score_confidence(strength="normal", mode="A", volume_ratio=1.5, cci=None, bb_pct_b=None, bad_rate=0.0) == 60


def test_volume_1_0x_no_bonus() -> None:
    assert score_confidence(strength="normal", mode="A", volume_ratio=1.0, cci=None, bb_pct_b=None, bad_rate=0.0) == 50


def test_cci_extreme_adds_10_mode_a() -> None:
    assert score_confidence(strength="normal", mode="A", volume_ratio=None, cci=-150.0, bb_pct_b=None, bad_rate=0.0) == 60


def test_cci_extreme_adds_10_mode_b() -> None:
    assert score_confidence(strength="normal", mode="B", volume_ratio=None, cci=200.0, bb_pct_b=None, bad_rate=0.0) == 60


def test_cci_extreme_not_applied_mode_c() -> None:
    assert score_confidence(strength="normal", mode="C", volume_ratio=None, cci=300.0, bb_pct_b=None, bad_rate=0.0) == 50


def test_bb_extreme_low_adds_10_mode_a() -> None:
    assert score_confidence(strength="normal", mode="A", volume_ratio=None, cci=None, bb_pct_b=0.0, bad_rate=0.0) == 60


def test_bb_extreme_high_adds_10_mode_a() -> None:
    assert score_confidence(strength="normal", mode="A", volume_ratio=None, cci=None, bb_pct_b=1.0, bad_rate=0.0) == 60


def test_bb_extreme_not_applied_mode_b() -> None:
    assert score_confidence(strength="normal", mode="B", volume_ratio=None, cci=None, bb_pct_b=0.0, bad_rate=0.0) == 50


def test_all_fields_present_adds_10() -> None:
    # vol=1.0 → no vol bonus; cci=-50 → abs(50)<150, no cci bonus; bb=0.5 → not extreme, no bb bonus
    # → base 50 + fields 10 = 60
    assert score_confidence(strength="normal", mode="A", volume_ratio=1.0, cci=-50.0, bb_pct_b=0.5, bad_rate=0.0) == 60


def test_bad_rate_40_subtracts_20() -> None:
    assert score_confidence(strength="normal", mode="A", volume_ratio=None, cci=None, bb_pct_b=None, bad_rate=40.0) == 30


def test_bad_rate_25_subtracts_10() -> None:
    assert score_confidence(strength="normal", mode="A", volume_ratio=None, cci=None, bb_pct_b=None, bad_rate=25.0) == 40


def test_bad_rate_below_25_no_penalty() -> None:
    assert score_confidence(strength="normal", mode="A", volume_ratio=None, cci=None, bb_pct_b=None, bad_rate=24.9) == 50


def test_clamp_max_100() -> None:
    # STRONG(+15) + vol≥2x(+20) + CCI≥150(+10) + BB extreme(+10) + all fields(+10) = 115 → 100
    assert score_confidence(strength="STRONG", mode="A", volume_ratio=2.0, cci=-200.0, bb_pct_b=-0.1, bad_rate=0.0) == 100


def test_clamp_min_0() -> None:
    result = score_confidence(strength="normal", mode="A", volume_ratio=None, cci=None, bb_pct_b=None, bad_rate=100.0)
    assert result >= 0
