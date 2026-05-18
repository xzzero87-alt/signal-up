"""friendly_validation_errors 단위 테스트 — M14 한국어 검증 메시지."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field, ValidationError

from signal_program.web.security import friendly_validation_errors


class _TestModel(BaseModel):
    value_ge: int = Field(ge=2)
    value_gt: float = Field(gt=0)
    value_le: int = Field(le=100)
    name: str


def _make_error(model_cls: type, data: dict) -> ValidationError:
    with pytest.raises(ValidationError) as exc_info:
        model_cls(**data)
    return exc_info.value


def test_greater_than_equal_korean() -> None:
    exc = _make_error(_TestModel, {"value_ge": 0, "value_gt": 1.0, "value_le": 50, "name": "x"})
    errors = friendly_validation_errors(exc)
    ge_errors = [e for e in errors if e["field"] == "value_ge"]
    assert ge_errors
    assert "이상이어야 합니다" in ge_errors[0]["message"]


def test_greater_than_korean() -> None:
    exc = _make_error(_TestModel, {"value_ge": 5, "value_gt": 0.0, "value_le": 50, "name": "x"})
    errors = friendly_validation_errors(exc)
    gt_errors = [e for e in errors if e["field"] == "value_gt"]
    assert gt_errors
    assert "보다 커야 합니다" in gt_errors[0]["message"]


def test_less_than_equal_korean() -> None:
    exc = _make_error(_TestModel, {"value_ge": 5, "value_gt": 1.0, "value_le": 200, "name": "x"})
    errors = friendly_validation_errors(exc)
    le_errors = [e for e in errors if e["field"] == "value_le"]
    assert le_errors
    assert "이하여야 합니다" in le_errors[0]["message"]


def test_missing_field_korean() -> None:
    exc = _make_error(_TestModel, {"value_ge": 5, "value_gt": 1.0, "value_le": 50})
    errors = friendly_validation_errors(exc)
    missing = [e for e in errors if e["field"] == "name"]
    assert missing
    assert "필수 항목" in missing[0]["message"]


def test_friendly_errors_returns_list() -> None:
    exc = _make_error(_TestModel, {"value_ge": 0, "value_gt": 0.0, "value_le": 200, "name": "x"})
    errors = friendly_validation_errors(exc)
    assert isinstance(errors, list)
    assert all("field" in e and "message" in e for e in errors)


def test_friendly_errors_field_path_includes_nested_keys() -> None:
    exc = _make_error(_TestModel, {"value_ge": 0, "value_gt": 1.0, "value_le": 50, "name": "x"})
    errors = friendly_validation_errors(exc)
    assert any("value_ge" in e["field"] for e in errors)


# ── Location prefix 제거 테스트 (M16 follow-up v2) ───────────────────────────


class _MockExc:
    """ValidationError를 흉내 내는 테스트 더블. loc를 직접 주입할 수 있다."""

    def __init__(self, raw_errors: list[dict]) -> None:
        self._raw = raw_errors

    def errors(self) -> list[dict]:
        return self._raw


def test_strips_body_prefix_from_field_path() -> None:
    """FastAPI body 검증 loc ('body', 'bb_period') → field='bb_period'."""
    exc = _MockExc([{
        "loc": ("body", "bb_period"),
        "type": "greater_than_equal",
        "ctx": {"ge": 2},
        "msg": "Input should be greater than or equal to 2",
    }])
    errors = friendly_validation_errors(exc)
    assert errors[0]["field"] == "bb_period"


def test_strips_query_prefix_from_field_path() -> None:
    """FastAPI query 파라미터 검증 loc ('query', 'market') → field='market'."""
    exc = _MockExc([{
        "loc": ("query", "market"),
        "type": "missing",
        "msg": "Field required",
    }])
    errors = friendly_validation_errors(exc)
    assert errors[0]["field"] == "market"


def test_preserves_nested_field_paths() -> None:
    """중첩 경로 ('body', 'nested', 'key') → field='nested.key' — 첫 요소만 제거."""
    exc = _MockExc([{
        "loc": ("body", "nested", "key"),
        "type": "missing",
        "msg": "Field required",
    }])
    errors = friendly_validation_errors(exc)
    assert errors[0]["field"] == "nested.key"


def test_handles_unknown_prefix_gracefully() -> None:
    """알 수 없는 prefix ('foo', 'bar') → field='foo.bar' — 변환 없음."""
    exc = _MockExc([{
        "loc": ("foo", "bar"),
        "type": "missing",
        "msg": "Field required",
    }])
    errors = friendly_validation_errors(exc)
    assert errors[0]["field"] == "foo.bar"


# ── 타입 mismatch 한국어 변환 (M16 follow-up v3) ─────────────────────────────


def test_string_type_returns_korean_message() -> None:
    """string_type 에러 → '문자열로 입력해야 합니다'."""
    exc = _MockExc([{
        "loc": ("telegram_chat_id",),
        "type": "string_type",
        "msg": "Input should be a valid string",
    }])
    errors = friendly_validation_errors(exc)
    assert errors[0]["message"] == "문자열로 입력해야 합니다"


def test_int_type_returns_korean_message() -> None:
    """int_type 에러 → '정수로 입력해야 합니다'."""
    exc = _MockExc([{
        "loc": ("bb_period",),
        "type": "int_type",
        "msg": "Input should be a valid integer",
    }])
    errors = friendly_validation_errors(exc)
    assert errors[0]["message"] == "정수로 입력해야 합니다"


def test_float_type_returns_korean_message() -> None:
    """float_type 에러 → '숫자로 입력해야 합니다'."""
    exc = _MockExc([{
        "loc": ("bb_std_mult",),
        "type": "float_type",
        "msg": "Input should be a valid number",
    }])
    errors = friendly_validation_errors(exc)
    assert errors[0]["message"] == "숫자로 입력해야 합니다"


def test_bool_type_returns_korean_message() -> None:
    """bool_type 에러 → '참/거짓 값으로 입력해야 합니다'."""
    exc = _MockExc([{
        "loc": ("dry_run",),
        "type": "bool_type",
        "msg": "Input should be a valid boolean",
    }])
    errors = friendly_validation_errors(exc)
    assert errors[0]["message"] == "참/거짓 값으로 입력해야 합니다"
