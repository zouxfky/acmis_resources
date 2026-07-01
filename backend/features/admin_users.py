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
    delete_user_home_on_any_container,
    fetch_user_joined_container_rows,
    rename_container_user_home,
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User does not exist")
        old_username = str(existing["username"])
        username_changed = username != old_username
        if admin_user["id"] == user_id and role != "admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove admin role from the current account")
        if existing["role"] == "admin":
            if username_changed:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin usernames cannot be changed")
            if role != "admin":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin accounts cannot remove admin role")
        if username_changed:
            duplicate_user = connection.execute(
                "SELECT 1 FROM users WHERE username = ? AND id != ? LIMIT 1",
                (username, user_id),
            ).fetchone()
            if duplicate_user:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

        joined_container_rows = fetch_user_joined_container_rows(user_id)
        joined_container_ids = [int(row["id"]) for row in joined_container_rows]
        lock_items = [(container_id, user_id) for container_id in joined_container_ids]

        with acquire_container_user_sync_locks(lock_items):
            renamed_container_ids: list[int] = []
            if username_changed:
                try:
                    for container_id in joined_container_ids:
                        rename_container_user_home(
                            container_id,
                            user_id,
                            old_username,
                            username,
                            allow_inactive=True,
                        )
                        renamed_container_ids.append(container_id)
                except Exception as exc:
                    for rollback_container_id in reversed(renamed_container_ids):
                        try:
                            rename_container_user_home(
                                rollback_container_id,
                                user_id,
                                username,
                                old_username,
                                allow_inactive=True,
                            )
                        except Exception:
                            pass
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Remote username migration failed; database was not updated",
                    ) from exc

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
                connection.rollback()
                if username_changed:
                    for rollback_container_id in reversed(renamed_container_ids):
                        try:
                            rename_container_user_home(
                                rollback_container_id,
                                user_id,
                                username,
                                old_username,
                                allow_inactive=True,
                            )
                        except Exception:
                            pass
                if "users.username" in str(exc):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists") from exc
                raise
            except Exception as exc:
                connection.rollback()
                if username_changed:
                    for rollback_container_id in reversed(renamed_container_ids):
                        try:
                            rename_container_user_home(
                                rollback_container_id,
                                user_id,
                                username,
                                old_username,
                                allow_inactive=True,
                            )
                        except Exception:
                            pass
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User update failed") from exc

        if joined_container_rows:
            for container_id in joined_container_ids:
                try:
                    sync_container_user_authorized_keys(container_id, user_id, allow_inactive=True)
                except Exception:
                    pass

        updated = _fetch_admin_user_detail(connection, user_id)
    return {"ok": True, "item": serialize_user(updated), "message": "User updated"}


@router.delete("/api/admin/users/{user_id}")
def delete_admin_user(user_id: int, request: Request) -> dict:
    admin_user = require_admin_user(request, require_csrf=True)
    if admin_user["id"] == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete the current admin account")

    with get_connection() as connection:
        existing = connection.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User does not exist")
        if existing["role"] == "admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin accounts cannot be deleted")
        username = str(existing["username"])

    delete_user_home_on_any_container(username)

    with get_connection() as connection:
        existing = connection.execute("SELECT id, role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User does not exist")
        if existing["role"] == "admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin accounts cannot be deleted")
        connection.execute("DELETE FROM user_ssh_key_bindings WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        cleanup_orphaned_ssh_keys(connection)
        connection.commit()

    return {"ok": True, "message": "用户已删除"}
