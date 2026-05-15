"""HTTP Basic Auth 미들웨어 — M16.

BasicAuthMiddleware:
  - bind이 localhost(127.0.0.1/::1/localhost)이면 완전 비활성
  - 비-localhost bind: 모든 요청에 Authorization Basic 헤더 필요
  - client.host가 localhost이면 bypass
  - secrets.compare_digest로 timing attack 방어. 사용자명: admin 고정
"""

from __future__ import annotations

import base64
import secrets
from typing import Any

_LOCALHOST_BINDS = frozenset({"127.0.0.1", "::1", "localhost"})
_LOCALHOST_CLIENT_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class BasicAuthMiddleware:
    """ASGI 미들웨어. 비-localhost 바인드 시 HTTP Basic Auth 강제."""

    def __init__(
        self,
        app: Any,
        *,
        bind: str,
        password: str | None,
    ) -> None:
        self._app = app
        self._active = bind not in _LOCALHOST_BINDS
        self._password = password or ""

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if not self._active or scope.get("type") not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        client = scope.get("client")
        host = client[0] if client else "127.0.0.1"
        if host in _LOCALHOST_CLIENT_HOSTS:
            await self._app(scope, receive, send)
            return

        headers: dict[bytes, bytes] = dict(scope.get("headers", []))
        auth_raw = headers.get(b"authorization", b"")
        auth_str = auth_raw.decode("latin-1", errors="ignore")

        if not auth_str.startswith("Basic "):
            await self._send_401(scope, receive, send)
            return

        try:
            decoded = base64.b64decode(auth_str[6:]).decode("utf-8", errors="ignore")
            username, _, password = decoded.partition(":")
        except Exception:  # noqa: BLE001
            await self._send_401(scope, receive, send)
            return

        if username != "admin" or not secrets.compare_digest(password, self._password):
            await self._send_401(scope, receive, send)
            return

        await self._app(scope, receive, send)

    async def _send_401(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"text/plain; charset=utf-8"),
                        (b"www-authenticate", b'Basic realm="signal"'),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": b"Unauthorized"})
