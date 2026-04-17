from fastapi import APIRouter, HTTPException, Request, Response, status

from backend.core.config import (
    COOKIE_SECURE,
    DEFAULT_MAX_CONTAINERS_PER_USER,
    RUNTIME_MONITOR_INTERVAL_SECONDS,
    SESSION_COOKIE,
    SESSION_MAX_AGE,
)
from backend.core.db import get_connection
from backend.core.helpers import serialize_user
from backend.core.security import (
    cleanup_expired_sessions,
    clear_login_failures,
    create_session,
    ensure_login_allowed,
    get_client_ip,
    get_login_rate_limit_scopes,
    hash_password,
    record_login_failure,
    require_authenticated_user,
    verify_password,
)
from backend.schemas import ChangePasswordPayload, LoginPayload


router = APIRouter()


def fetch_public_overview() -> dict:
    return {
        "notice_lines": [
            f"每位用户最多可同时接入 {DEFAULT_MAX_CONTAINERS_PER_USER} 台容器，支持多设备并行连接",
            "仅开放 /home/<用户名> 目录权限，数据盘支持跨容器共享",
            f"平台运行监控按 {RUNTIME_MONITOR_INTERVAL_SECONDS}s 刷新，资源状态会有短暂延迟",
            "如遇资源冲突，可先悬浮查看容器占用中的当前用户，再结合 GPU 进程信息沟通协调",
        ],
    }


@router.get("/api/health")
def healthcheck() -> dict:
    return {"status": "ok"}


@router.get("/api/public/overview")
def get_public_overview() -> dict:
    return fetch_public_overview()


@router.get("/api/session")
def get_session(request: Request) -> dict:
    user = require_authenticated_user(request)
    return {"user": serialize_user(user), "csrf_token": user["csrf_token"]}


@router.post("/api/login")
def login(payload: LoginPayload, request: Request, response: Response) -> dict:
    username = payload.username.strip()
    client_ip = get_client_ip(request)
    scopes = get_login_rate_limit_scopes(username, client_ip)

    with get_connection() as connection:
        cleanup_expired_sessions(connection)
        ensure_login_allowed(connection, scopes)

        user = connection.execute(
            """
            SELECT
                id,
                username,
                real_name,
                password_hash,
                role,
                status,
                max_ssh_keys_per_user,
                max_join_keys_per_request,
                max_containers_per_user
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

        if not user or user["status"] != "active" or not verify_password(payload.password, user["password_hash"]):
            record_login_failure(connection, scopes)
            connection.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )

        clear_login_failures(connection, scopes)
        session_token, csrf_token, _ = create_session(connection, user["id"])
        connection.commit()

    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return {"user": serialize_user(user), "csrf_token": csrf_token}


@router.post("/api/logout")
def logout(request: Request, response: Response) -> dict:
    user = require_authenticated_user(request, require_csrf=True)
    with get_connection() as connection:
        connection.execute("DELETE FROM user_sessions WHERE id = ?", (user["session_id"],))
        connection.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/api/change-password")
def change_password(payload: ChangePasswordPayload, request: Request, response: Response) -> dict:
    user = require_authenticated_user(request, require_csrf=True)

    if not verify_password(payload.current_password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前密码错误")

    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能与当前密码相同")

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET password_hash = ?
            WHERE id = ?
            """,
            (hash_password(payload.new_password), user["id"]),
        )
        connection.execute("DELETE FROM user_sessions WHERE user_id = ?", (user["id"],))
        session_token, csrf_token, _ = create_session(connection, user["id"])
        connection.commit()
        refreshed_user = connection.execute(
            """
            SELECT
                id,
                username,
                real_name,
                role,
                status,
                max_ssh_keys_per_user,
                max_join_keys_per_request,
                max_containers_per_user
            FROM users
            WHERE id = ?
            """,
            (user["id"],),
        ).fetchone()

    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return {
        "ok": True,
        "message": "密码修改成功",
        "user": serialize_user(refreshed_user),
        "csrf_token": csrf_token,
    }
