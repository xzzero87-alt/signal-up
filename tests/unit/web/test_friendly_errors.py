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
