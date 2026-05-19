"""웹 보안 헬퍼 — 시크릿 마스킹 + 바인드 안전 가드.

ADR-0007: 시크릿(TELEGRAM_BOT_TOKEN 등) 응답 평문 노출 금지
ADR-0005: WEB_BIND 비-localhost + 빈 비밀번호 → 시작 거부
M14 추가: friendly_validation_errors (Pydantic → 한국어 메시지)
"""

from __future__ import annotations

import sys
from typing import Any

_SECRET_FIELDS: frozenset[str] = frozenset({"telegram_bot_token", "web_auth_password"})


def mask_secret_value(value: str) -> str:
    """시크릿 값을 '••••••••XXXX' 형태로 마스킹한다. 빈 문자열은 그대로."""
    if not value:
        return ""
    visible = value[-4:] if len(value) >= 4 else value
    return f"••••••••{visible}"


def mask_secrets(view: dict[str, Any]) -> dict[str, Any]:
    """dict의 알려진 시크릿 필드를 마스킹한다."""
    result = dict(view)
    for field in _SECRET_FIELDS:
        if field in result and isinstance(result[field], str):
            result[field] = mask_secret_value(result[field])
    return result


def assert_safe_bind(bind: str, password: str | None) -> None:
    """비-localhost + 빈 비밀번호 조합을 거부한다.

    DESIGN.md §10: WEB_BIND != 127.0.0.1 시 WEB_AUTH_PASSWORD 필수.
    """
    if bind == "127.0.0.1":
        return
    if not password:
        msg = (
            f"[오류] WEB_BIND={bind!r}는 비-localhost이지만 WEB_AUTH_PASSWORD 미설정. "
            "보안을 위해 시작을 거부합니다."
        )
        print(msg, file=sys.stderr)
        sys.exit(1)


_REQUEST_LOCATION_PREFIXES: frozenset[str] = frozenset(
    {"body", "query", "path", "header", "cookie"}
)


def friendly_validation_errors(exc: Any) -> list[dict[str, str]]:
    """Pydantic ValidationError → 한국어 필드별 메시지.

    FastAPI request 검증 시 loc 첫 요소는 'body'/'query'/'path' 등 위치 prefix.
    응답에는 필드 이름만 노출 (예: "bb_period", "nested.key").

    반환: [{"field": "bb_period", "message": "2 이상이어야 합니다"}]
    """
    messages = []
    for err in exc.errors():
        loc = list(err["loc"])
        if loc and isinstance(loc[0], str) and loc[0] in _REQUEST_LOCATION_PREFIXES:
            loc = loc[1:]
        field = ".".join(str(p) for p in loc)
        ctx = err.get("ctx", {})
        match err["type"]:
            case "greater_than_equal":
                messages.append({"field": field, "message": f"{ctx.get('ge')} 이상이어야 합니다"})
            case "greater_than":
                messages.append({"field": field, "message": f"{ctx.get('gt')}보다 커야 합니다"})
            case "less_than_equal":
                messages.append({"field": field, "message": f"{ctx.get('le')} 이하여야 합니다"})
            case "less_than":
                messages.append({"field": field, "message": f"{ctx.get('lt')}보다 작아야 합니다"})
            case "missing":
                messages.append({"field": field, "message": "필수 항목입니다"})
            case "string_pattern_mismatch":
                messages.append({"field": field, "message": "형식이 올바르지 않습니다"})
            case "string_type":
                messages.append({"field": field, "message": "문자열로 입력해야 합니다"})
            case "int_type" | "int_parsing":
                messages.append({"field": field, "message": "정수로 입력해야 합니다"})
            case "float_type" | "float_parsing" | "decimal_type" | "decimal_parsing":
                messages.append({"field": field, "message": "숫자로 입력해야 합니다"})
            case "bool_type" | "bool_parsing":
                messages.append({"field": field, "message": "참/거짓 값으로 입력해야 합니다"})
            case "string_too_short":
                min_len = ctx.get("min_length")
                messages.append({"field": field, "message": f"최소 {min_len}자 이상 입력하세요"})
            case "string_too_long":
                max_len = ctx.get("max_length")
                messages.append({"field": field, "message": f"최대 {max_len}자 이하로 입력하세요"})
            case "value_error":
                # ValueError에서 "Value error, " prefix 제거하고 한국어 메시지만 표시
                raw = str(ctx.get("error", err["msg"]))
                messages.append({"field": field, "message": raw})
            case _:
                messages.append({"field": field, "message": err["msg"]})
    return messages
