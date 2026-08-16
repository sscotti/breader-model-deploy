#!/usr/bin/env python3
"""Caddy forward_auth backend: HTTP Basic Auth + per-IP lockout after N bad passwords."""

from __future__ import annotations

import base64
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import bcrypt

USERS_FILE = Path(os.environ.get("AUTHGATE_USERS_FILE", "/auth/users.basicauth"))
MAX_FAILURES = int(os.environ.get("AUTHGATE_MAX_FAILURES", "3"))
LOCKOUT_SECONDS = int(os.environ.get("AUTHGATE_LOCKOUT_SECONDS", "900"))
LISTEN = os.environ.get("AUTHGATE_LISTEN", "0.0.0.0")
PORT = int(os.environ.get("AUTHGATE_PORT", "9090"))
REALM = os.environ.get("AUTHGATE_REALM", "B-reader demo")
AUTH_ENABLED = os.environ.get("AUTHGATE_ENABLED", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

_lock = threading.Lock()
# ip -> {"fails": int, "locked_until": float}
_state: dict[str, dict[str, float | int]] = {}
_users: dict[str, bytes] = {}
_users_mtime: float | None = None


def _load_users(force: bool = False) -> None:
    global _users, _users_mtime
    if not USERS_FILE.is_file():
        raise FileNotFoundError(f"users file missing: {USERS_FILE}")
    mtime = USERS_FILE.stat().st_mtime
    if not force and _users_mtime == mtime:
        return
    users: dict[str, bytes] = {}
    for line in USERS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        user, hashed = parts
        users[user] = hashed.encode("utf-8")
    if not users:
        raise ValueError(f"no users in {USERS_FILE}")
    _users = users
    _users_mtime = mtime


def _client_ip(handler: BaseHTTPRequestHandler) -> str:
    real = handler.headers.get("X-Real-IP") or handler.headers.get("X-Forwarded-For", "")
    if real:
        return real.split(",")[0].strip() or "unknown"
    return handler.client_address[0]


def _locked(ip: str, now: float) -> bool:
    row = _state.get(ip)
    if not row:
        return False
    until = float(row.get("locked_until", 0))
    return until > now


def _register_failure(ip: str, now: float) -> tuple[int, bool]:
    with _lock:
        row = _state.setdefault(ip, {"fails": 0, "locked_until": 0.0})
        if float(row["locked_until"]) > now:
            return int(row["fails"]), True
        fails = int(row["fails"]) + 1
        row["fails"] = fails
        if fails >= MAX_FAILURES:
            row["locked_until"] = now + LOCKOUT_SECONDS
            return fails, True
        return fails, False


def _clear_failures(ip: str) -> None:
    with _lock:
        _state.pop(ip, None)


def _check_basic(auth_header: str | None) -> tuple[bool, str | None]:
    """Return (ok, username). Missing/malformed/wrong -> not ok."""
    if not auth_header or not auth_header.lower().startswith("basic "):
        return False, None
    try:
        raw = base64.b64decode(auth_header.split(" ", 1)[1].strip(), validate=True)
        user_pass = raw.decode("utf-8")
        user, _, password = user_pass.partition(":")
    except Exception:
        return False, None
    if not user:
        return False, None
    _load_users()
    hashed = _users.get(user)
    if hashed is None:
        return False, user
    try:
        ok = bcrypt.checkpw(password.encode("utf-8"), hashed)
    except ValueError:
        return False, user
    return ok, user


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        sys_stderr = __import__("sys").stderr
        print(f"[authgate] {self.address_string()} {fmt % args}", file=sys_stderr, flush=True)

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] not in ("/verify", "/healthz"):
            self.send_error(404)
            return
        if self.path.startswith("/healthz"):
            self._respond(200, b"ok\n", "text/plain")
            return

        if not AUTH_ENABLED:
            self._respond(200, b"auth disabled\n", "text/plain")
            return

        ip = _client_ip(self)
        now = time.time()

        with _lock:
            if _locked(ip, now):
                row = _state.get(ip, {})
                retry = max(1, int(float(row.get("locked_until", now)) - now))
                body = (
                    f"Too many failed login attempts. Try again in {retry}s "
                    f"(limit {MAX_FAILURES} failures / {LOCKOUT_SECONDS}s lockout).\n"
                ).encode()
                self._respond(429, body, "text/plain", {"Retry-After": str(retry)})
                return

        auth = self.headers.get("Authorization")
        ok, user = _check_basic(auth)

        # No credentials yet: prompt browser; do not count as a strike.
        if auth is None or not auth.lower().startswith("basic "):
            self._respond(
                401,
                b"Unauthorized\n",
                "text/plain",
                {"WWW-Authenticate": f'Basic realm="{REALM}"'},
            )
            return

        if not ok:
            fails, locked = _register_failure(ip, now)
            if locked:
                body = (
                    f"Too many failed login attempts. Locked for {LOCKOUT_SECONDS}s "
                    f"after {MAX_FAILURES} failures.\n"
                ).encode()
                self._respond(
                    429,
                    body,
                    "text/plain",
                    {"Retry-After": str(LOCKOUT_SECONDS)},
                )
                return
            remaining = MAX_FAILURES - fails
            self._respond(
                401,
                f"Unauthorized ({remaining} attempt(s) left)\n".encode(),
                "text/plain",
                {"WWW-Authenticate": f'Basic realm="{REALM}"'},
            )
            return

        _clear_failures(ip)
        headers = {}
        if user:
            headers["Remote-User"] = user
        self._respond(200, b"ok\n", "text/plain", headers)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        # Gradio / API may POST; forward_auth still hits /verify with original method.
        self.do_GET()

    def do_OPTIONS(self) -> None:
        self.do_GET()

    def do_PUT(self) -> None:
        self.do_GET()

    def do_PATCH(self) -> None:
        self.do_GET()

    def do_DELETE(self) -> None:
        self.do_GET()

    def _respond(
        self,
        code: int,
        body: bytes,
        content_type: str,
        extra: dict[str, str] | None = None,
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


def main() -> None:
    if AUTH_ENABLED:
        _load_users(force=True)
        users_note = str(USERS_FILE)
    else:
        users_note = "disabled"
    server = ThreadingHTTPServer((LISTEN, PORT), Handler)
    print(
        f"[authgate] listening on {LISTEN}:{PORT} "
        f"(enabled={AUTH_ENABLED}, max_failures={MAX_FAILURES}, "
        f"lockout={LOCKOUT_SECONDS}s, users={users_note})",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
