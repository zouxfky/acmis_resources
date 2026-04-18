import base64
from collections import deque
import hashlib
import hmac
import secrets
import sqlite3
from threading import Lock
import time
from typing import Optional

from fastapi import HTTPException, Request, status

from backend.core.config import (
    LOGIN_LOCK_SECONDS,
    LOGIN_MAX_FAILURES_PER_IP,
    LOGIN_MAX_FAILURES_PER_USERNAME,
    LOGIN_WINDOW_SECONDS,
    PASSWORD_SCHEME,
    PBKDF2_ITERATIONS,
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    SESSION_TOUCH_INTERVAL_SECONDS,
    TRUST_PROXY_HEADERS,
)
from backend.core.db import get_connection


REQUEST_RATE_LIMIT_LOCK = Lock()
REQUEST_RATE_LIMIT_BUCKETS: dict[str, dict[str, object]] = {}


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return (
        f"{PASSWORD_SCHEME}${PBKDF2_ITERATIONS}${salt}$"
        f"{base64.urlsafe_b64encode(digest).decode('utf-8')}"
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_text, salt, encoded_hash = stored_hash.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations_text),
        )
        expected = base64.urlsafe_b64decode(encoded_hash.encode("utf-8"))
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(connection: sqlite3.Connection, user_id: int) -> tuple[str, str, int]:
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    expires_at = int(time.time()) + SESSION_MAX_AGE
    connection.execute(
        """
        INSERT INTO user_sessions (
            user_id,
            session_token_hash,
            csrf_token,
            expires_at,
            created_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (user_id, hash_session_token(session_token), csrf_token, expires_at),
    )
    return session_token, csrf_token, expires_at


def cleanup_expired_sessions(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        DELETE FROM user_sessions
        WHERE expires_at < ?
        """,
        (int(time.time()),),
    )


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if TRUST_PROXY_HEADERS and forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_route_path(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if route_path:
        return str(route_path)
    return request.url.path


def get_request_rate_limit_profile(request: Request) -> tuple[int, int, dict[str, int]]:
    route_path = get_route_path(request)
    method = request.method.upper()

    if route_path == "/api/session":
        return 10, 20, {"ip": 30, "user": 20, "route": 200}
    if route_path.endswith("/runtime"):
        return 10, 20, {"ip": 60, "user": 40, "route": 300}
    if route_path.startswith("/api/admin") and method in {"POST", "PUT", "DELETE"}:
        return 30, 60, {"ip": 30, "user": 20, "route": 160}
    if method in {"POST", "PUT", "DELETE"}:
        return 20, 45, {"ip": 40, "user": 30, "route": 200}
    if route_path.startswith("/api/admin"):
        return 15, 20, {"ip": 50, "user": 35, "route": 220}
    return 10, 20, {"ip": 80, "user": 50, "route": 320}


def prune_request_rate_limit_bucket(timestamps: deque[float], window_seconds: int, now: float) -> None:
    cutoff = now - window_seconds
    while timestamps and timestamps[0] <= cutoff:
        timestamps.popleft()


def prune_request_rate_limit_state(now: float) -> None:
    stale_keys: list[str] = []
    for scope_key, state in REQUEST_RATE_LIMIT_BUCKETS.items():
        timestamps = state["timestamps"]
        blocked_until = float(state["blocked_until"])
        if not timestamps and blocked_until <= now:
            stale_keys.append(scope_key)
    for scope_key in stale_keys:
        REQUEST_RATE_LIMIT_BUCKETS.pop(scope_key, None)


def enforce_request_rate_limit(request: Request, user_id: int) -> None:
    route_path = get_route_path(request)
    if route_path in {"/api/health", "/api/login"}:
        return

    window_seconds, block_seconds, limits = get_request_rate_limit_profile(request)
    now = time.time()
    scope_entries = [
        (f"request:ip:{get_client_ip(request)}", limits["ip"]),
        (f"request:user:{user_id}", limits["user"]),
        (f"request:route:{request.method.upper()}:{route_path}", limits["route"]),
    ]

    with REQUEST_RATE_LIMIT_LOCK:
        prune_request_rate_limit_state(now)
        states: list[tuple[str, int, dict[str, object]]] = []
        for scope_key, max_requests in scope_entries:
            state = REQUEST_RATE_LIMIT_BUCKETS.setdefault(
                scope_key,
                {"timestamps": deque(), "blocked_until": 0.0},
            )
            timestamps = state["timestamps"]
            prune_request_rate_limit_bucket(timestamps, window_seconds, now)
            blocked_until = float(state["blocked_until"])
            if blocked_until > now:
                retry_after = max(1, int(blocked_until - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"请求过于频繁，请在 {retry_after} 秒后重试",
                )
            if len(timestamps) >= max_requests:
                state["blocked_until"] = now + block_seconds
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"请求过于频繁，请在 {block_seconds} 秒后重试",
                )
            states.append((scope_key, max_requests, state))

        for _, _, state in states:
            state["timestamps"].append(now)


def get_login_rate_limit_scopes(username: str, client_ip: str) -> list[tuple[str, int]]:
    scopes = [(f"ip:{client_ip}", LOGIN_MAX_FAILURES_PER_IP)]
    if username:
        scopes.append((f"user:{username.lower()}", LOGIN_MAX_FAILURES_PER_USERNAME))
    return scopes


def ensure_login_allowed(connection: sqlite3.Connection, scopes: list[tuple[str, int]]) -> None:
    if not scopes:
        return

    now = int(time.time())
    placeholders = ",".join("?" for _ in scopes)
    rows = connection.execute(
        f"""
        SELECT scope_key, locked_until
        FROM login_rate_limits
        WHERE scope_key IN ({placeholders})
        """,
        [scope_key for scope_key, _ in scopes],
    ).fetchall()

    active_locks = [
        int(row["locked_until"])
        for row in rows
        if row["locked_until"] and int(row["locked_until"]) > now
    ]
    if active_locks:
        retry_after = max(1, min(active_locks) - now)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录尝试过于频繁，请在 {retry_after} 秒后重试",
        )


def record_login_failure(connection: sqlite3.Connection, scopes: list[tuple[str, int]]) -> None:
    now = int(time.time())
    for scope_key, max_failures in scopes:
        row = connection.execute(
            """
            SELECT failure_count, first_failed_at, locked_until
            FROM login_rate_limits
            WHERE scope_key = ?
            """,
            (scope_key,),
        ).fetchone()

        if row and row["first_failed_at"] and int(row["first_failed_at"]) > now - LOGIN_WINDOW_SECONDS:
            failure_count = int(row["failure_count"]) + 1
            first_failed_at = int(row["first_failed_at"])
        else:
            failure_count = 1
            first_failed_at = now

        locked_until = now + LOGIN_LOCK_SECONDS if failure_count >= max_failures else 0
        connection.execute(
            """
            INSERT INTO login_rate_limits (
                scope_key,
                failure_count,
                first_failed_at,
                locked_until,
                updated_at
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(scope_key) DO UPDATE SET
                failure_count = excluded.failure_count,
                first_failed_at = excluded.first_failed_at,
                locked_until = excluded.locked_until,
                updated_at = CURRENT_TIMESTAMP
            """,
            (scope_key, failure_count, first_failed_at, locked_until),
        )


def clear_login_failures(connection: sqlite3.Connection, scopes: list[tuple[str, int]]) -> None:
    if not scopes:
        return
    connection.executemany(
        "DELETE FROM login_rate_limits WHERE scope_key = ?",
        [(scope_key,) for scope_key, _ in scopes],
    )


def get_current_user(request: Request) -> Optional[sqlite3.Row]:
    session_token = request.cookies.get(SESSION_COOKIE)
    if not session_token:
        return None

    with get_connection() as connection:
        cleanup_expired_sessions(connection)
        session = connection.execute(
            """
            SELECT
                s.id AS session_id,
                s.user_id,
                s.csrf_token,
                s.expires_at,
                s.last_seen_at,
                u.id,
                u.username,
                u.real_name,
                u.password_hash,
                u.role,
                u.max_ssh_keys_per_user,
                u.max_join_keys_per_request,
                u.max_containers_per_user
            FROM user_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.session_token_hash = ?
            """,
            (hash_session_token(session_token),),
        ).fetchone()
        if not session:
            return None
        if int(session["expires_at"]) < int(time.time()):
            connection.execute("DELETE FROM user_sessions WHERE id = ?", (session["session_id"],))
            connection.commit()
            return None

        cursor = connection.execute(
            """
            UPDATE user_sessions
            SET last_seen_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND (
                  last_seen_at IS NULL
                  OR CAST(strftime('%s', last_seen_at) AS INTEGER) <= ?
              )
            """,
            (session["session_id"], int(time.time()) - SESSION_TOUCH_INTERVAL_SECONDS),
        )
        if cursor.rowcount > 0:
            connection.commit()
        return session


def validate_csrf(request: Request, csrf_token: str) -> None:
    header_token = request.headers.get("x-csrf-token", "").strip()
    if not header_token or not hmac.compare_digest(header_token, csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF 校验失败")


def require_admin_user(request: Request, require_csrf: bool = False) -> sqlite3.Row:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    enforce_request_rate_limit(request, user["id"])
    if require_csrf:
        validate_csrf(request, user["csrf_token"])
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def require_authenticated_user(request: Request, require_csrf: bool = False) -> sqlite3.Row:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    enforce_request_rate_limit(request, user["id"])
    if require_csrf:
        validate_csrf(request, user["csrf_token"])
    return user
