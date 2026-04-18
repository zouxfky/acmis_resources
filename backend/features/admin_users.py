import sqlite3

from fastapi import APIRouter, HTTPException, Request, status

from backend.core.db import allocate_next_linux_identity, get_connection
from backend.core.helpers import (
    normalize_optional_text,
    serialize_user,
    validate_linux_username,
    validate_user_role,
)
from backend.core.security import hash_password, require_admin_user
from backend.features.admin_shared import cleanup_orphaned_ssh_keys, fetch_admin_users
from backend.features.container_ssh_access import (
    acquire_container_user_sync_locks,
    fetch_user_joined_container_rows,
    sync_container_user_authorized_keys,
)
from backend.schemas import AdminUserCreatePayload, AdminUserUpdatePayload


router = APIRouter()


def _fetch_admin_user_detail(connection, user_id: int):
    return connection.execute(
        """
        SELECT
            id,
            username,
            real_name,
            role,
            linux_uid,
            linux_gid,
            max_ssh_keys_per_user,
            max_join_keys_per_request,
            max_containers_per_user
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()


@router.get("/api/admin/users")
def list_admin_users(request: Request) -> dict:
    require_admin_user(request)
    return {"items": fetch_admin_users()}


@router.post("/api/admin/users")
def create_admin_user(payload: AdminUserCreatePayload, request: Request) -> dict:
    require_admin_user(request, require_csrf=True)

    username = validate_linux_username(payload.username)
    role = validate_user_role(payload.role)
    real_name = normalize_optional_text(payload.real_name)

    try:
        with get_connection() as connection:
            linux_uid, linux_gid = allocate_next_linux_identity(connection)
            cursor = connection.execute(
                """
                INSERT INTO users (
                    username,
                    real_name,
                    password_hash,
                    role,
                    linux_uid,
                    linux_gid,
                    max_ssh_keys_per_user,
                    max_join_keys_per_request,
                    max_containers_per_user
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    real_name,
                    hash_password(payload.password),
                    role,
                    linux_uid,
                    linux_gid,
                    payload.max_ssh_keys_per_user,
                    payload.max_join_keys_per_request,
                    payload.max_containers_per_user,
                ),
            )
            connection.commit()
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError as exc:
        if "users.username" in str(exc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在") from exc
        raise

    with get_connection() as connection:
        user = _fetch_admin_user_detail(connection, int(user_id))
    return {"ok": True, "item": serialize_user(user), "message": "用户已创建"}


@router.put("/api/admin/users/{user_id}")
def update_admin_user(user_id: int, payload: AdminUserUpdatePayload, request: Request) -> dict:
    admin_user = require_admin_user(request, require_csrf=True)

    username = validate_linux_username(payload.username)
    role = validate_user_role(payload.role)
    real_name = normalize_optional_text(payload.real_name)
    new_password = normalize_optional_text(payload.new_password)

    with get_connection() as connection:
        existing = connection.execute(
            """
            SELECT id, username, role, linux_uid, linux_gid
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        if admin_user["id"] == user_id and role != "admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能移除当前登录账户的管理员角色")
        if existing["role"] == "admin":
            if username != str(existing["username"]):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="管理员账户暂不支持修改用户名")
            if role != "admin":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="管理员账户不能移除管理员角色")
        if username != str(existing["username"]):
            joined_container_row = connection.execute(
                """
                SELECT 1
                FROM ssh_key_container_bindings scb
                JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
                WHERE ub.user_id = ?
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            if joined_container_row:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="该用户已经接入过容器，暂不支持直接修改用户名",
                )

        joined_container_rows = fetch_user_joined_container_rows(user_id)
        active_container_ids = [int(row["id"]) for row in joined_container_rows if row["status"] == "active"]
        lock_items = [(container_id, user_id) for container_id in active_container_ids]

        with acquire_container_user_sync_locks(lock_items):
            try:
                if new_password:
                    connection.execute(
                        """
                        UPDATE users
                        SET
                            username = ?,
                            real_name = ?,
                            role = ?,
                            password_hash = ?,
                            max_ssh_keys_per_user = ?,
                            max_join_keys_per_request = ?,
                            max_containers_per_user = ?
                        WHERE id = ?
                        """,
                        (
                            username,
                            real_name,
                            role,
                            hash_password(new_password),
                            payload.max_ssh_keys_per_user,
                            payload.max_join_keys_per_request,
                            payload.max_containers_per_user,
                            user_id,
                        ),
                    )
                    connection.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
                else:
                    connection.execute(
                        """
                        UPDATE users
                        SET
                            username = ?,
                            real_name = ?,
                            role = ?,
                            max_ssh_keys_per_user = ?,
                            max_join_keys_per_request = ?,
                            max_containers_per_user = ?
                        WHERE id = ?
                        """,
                        (
                            username,
                            real_name,
                            role,
                            payload.max_ssh_keys_per_user,
                            payload.max_join_keys_per_request,
                            payload.max_containers_per_user,
                            user_id,
                        ),
                    )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                if "users.username" in str(exc):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在") from exc
                raise
            except Exception as exc:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="用户更新失败") from exc

            if joined_container_rows:
                for container_id in active_container_ids:
                    try:
                        sync_container_user_authorized_keys(container_id, user_id)
                    except Exception:
                        pass

        updated = _fetch_admin_user_detail(connection, user_id)
    return {"ok": True, "item": serialize_user(updated), "message": "用户已更新"}


@router.delete("/api/admin/users/{user_id}")
def delete_admin_user(user_id: int, request: Request) -> dict:
    admin_user = require_admin_user(request, require_csrf=True)
    if admin_user["id"] == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除当前登录的管理员账户")

    with get_connection() as connection:
        existing = connection.execute("SELECT id, role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        if existing["role"] == "admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="管理员账户不允许删除")
        joined_container_row = connection.execute(
            """
            SELECT 1
            FROM ssh_key_container_bindings scb
            JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
            WHERE ub.user_id = ?
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        if joined_container_row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该用户仍有容器接入记录，请先退出所有容器后再删除",
            )
        connection.execute("DELETE FROM user_ssh_key_bindings WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        cleanup_orphaned_ssh_keys(connection)
        connection.commit()
    return {"ok": True, "message": "用户已删除"}
