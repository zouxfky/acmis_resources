import sqlite3

from fastapi import APIRouter, HTTPException, Request, status

from backend.core.db import get_connection
from backend.core.helpers import (
    inspect_ssh_container_hardware,
    normalize_optional_text,
    serialize_user,
    validate_container_status,
    validate_linux_username,
    validate_ssh_root_login,
    validate_user_role,
    validate_user_status,
)
from backend.core.security import hash_password, require_admin_user
from backend.features.runtime import (
    build_runtime_payload_for_container,
    fetch_container_runtime_payload,
    fetch_runtime_snapshot_maps,
    upsert_container_runtime_system,
)
from backend.features.container_ssh_access import (
    acquire_container_user_sync_locks,
    fetch_user_joined_container_rows,
    sync_container_user_authorized_keys,
)
from backend.features.runtime_monitor import collect_container_runtime_now, enqueue_pending_container_user_sync
from backend.schemas import (
    AdminContainerCreatePayload,
    AdminContainerUpdatePayload,
    AdminUserCreatePayload,
    AdminUserUpdatePayload,
)


router = APIRouter()


def cleanup_orphaned_ssh_keys(connection: sqlite3.Connection) -> None:
    orphan_rows = connection.execute(
        """
        SELECT id
        FROM ssh_public_keys
        WHERE id NOT IN (
            SELECT ssh_key_id
            FROM user_ssh_key_bindings
        )
        """
    ).fetchall()
    orphan_ids = [row["id"] for row in orphan_rows]
    if not orphan_ids:
        return

    connection.executemany(
        "DELETE FROM ssh_key_container_bindings WHERE ssh_key_id = ?",
        [(key_id,) for key_id in orphan_ids],
    )
    connection.executemany(
        "DELETE FROM ssh_public_keys WHERE id = ?",
        [(key_id,) for key_id in orphan_ids],
    )


def fetch_admin_users() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                u.id,
                u.username,
                u.real_name,
                u.role,
                u.status,
                u.max_ssh_keys_per_user,
                u.max_join_keys_per_request,
                u.max_containers_per_user,
                COUNT(DISTINCT ub.ssh_key_id) AS ssh_key_count,
                COUNT(DISTINCT scb.container_id) AS access_count
            FROM users u
            LEFT JOIN user_ssh_key_bindings ub ON ub.user_id = u.id
            LEFT JOIN ssh_key_container_bindings scb ON scb.ssh_key_id = ub.ssh_key_id
            GROUP BY
                u.id, u.username, u.real_name, u.role, u.status,
                u.max_ssh_keys_per_user, u.max_join_keys_per_request, u.max_containers_per_user
            ORDER BY u.id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_admin_containers() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                c.id,
                c.name,
                c.host,
                c.ssh_port,
                CASE WHEN COALESCE(c.root_password, '') = '' THEN 0 ELSE 1 END AS has_root_password,
                c.max_users,
                c.gpu_model,
                c.gpu_memory,
                c.gpu_count,
                c.cpu_cores,
                c.memory_size,
                c.status,
                COUNT(DISTINCT ub.user_id) AS active_user_count
            FROM containers c
            LEFT JOIN ssh_key_container_bindings scb ON scb.container_id = c.id
            LEFT JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
            GROUP BY
                c.id, c.name, c.host, c.ssh_port, c.root_password, c.max_users,
                c.gpu_model, c.gpu_memory, c.gpu_count, c.cpu_cores, c.memory_size, c.status
            ORDER BY c.id ASC
            """
        ).fetchall()
        system_map, gpu_runtime_map, _ = fetch_runtime_snapshot_maps(connection)

    items = []
    for row in rows:
        runtime_payload = build_runtime_payload_for_container(
            row,
            system_map.get(row["id"]),
            gpu_runtime_map.get(row["id"], []),
        )
        item = dict(row)
        item.update(
            {
                "gpu_usage_percent": runtime_payload["gpu_usage_percent"],
                "gpu_usage_summary": runtime_payload["gpu_usage_summary"],
                "cpu_usage_percent": runtime_payload["cpu_usage_percent"],
                "cpu_usage_summary": runtime_payload["cpu_usage_summary"],
                "memory_usage_percent": runtime_payload["memory_usage_percent"],
                "memory_usage_summary": runtime_payload["memory_usage_summary"],
                "runtime_updated_at": runtime_payload["runtime_updated_at"],
            }
        )
        items.append(item)
    return items


@router.get("/api/admin/users")
def list_admin_users(request: Request) -> dict:
    require_admin_user(request)
    return {"items": fetch_admin_users()}


@router.post("/api/admin/users")
def create_admin_user(payload: AdminUserCreatePayload, request: Request) -> dict:
    require_admin_user(request, require_csrf=True)

    username = validate_linux_username(payload.username)
    role = validate_user_role(payload.role)
    user_status = validate_user_status(payload.status)
    real_name = normalize_optional_text(payload.real_name)

    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (
                    username,
                    real_name,
                    password_hash,
                    role,
                    status,
                    max_ssh_keys_per_user,
                    max_join_keys_per_request,
                    max_containers_per_user
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    real_name,
                    hash_password(payload.password),
                    role,
                    user_status,
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
        user = connection.execute(
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
            (user_id,),
        ).fetchone()
    return {"ok": True, "item": serialize_user(user), "message": "用户已创建"}


@router.put("/api/admin/users/{user_id}")
def update_admin_user(user_id: int, payload: AdminUserUpdatePayload, request: Request) -> dict:
    admin_user = require_admin_user(request, require_csrf=True)

    username = validate_linux_username(payload.username)
    role = validate_user_role(payload.role)
    user_status = validate_user_status(payload.status)
    real_name = normalize_optional_text(payload.real_name)
    new_password = normalize_optional_text(payload.new_password)

    with get_connection() as connection:
        existing = connection.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        if existing["role"] == "admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="管理员账户不允许编辑")
        if admin_user["id"] == user_id and user_status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能禁用当前登录的管理员账户")
        if admin_user["id"] == user_id and role != "admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能移除当前登录账户的管理员角色")
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

        status_changed = user_status != str(existing["status"])
        joined_container_rows = fetch_user_joined_container_rows(user_id) if status_changed else []
        lock_items = [(int(row["id"]), user_id) for row in joined_container_rows]
        active_container_ids = [int(row["id"]) for row in joined_container_rows if row["status"] == "active"]
        offline_container_ids = [int(row["id"]) for row in joined_container_rows if row["status"] != "active"]

        with acquire_container_user_sync_locks(lock_items):
            if status_changed and user_status == "disabled":
                synced_active_container_ids: list[int] = []
                try:
                    for container_id in active_container_ids:
                        sync_container_user_authorized_keys(container_id, user_id, [])
                        synced_active_container_ids.append(container_id)
                except Exception:
                    for synced_container_id in synced_active_container_ids:
                        try:
                            sync_container_user_authorized_keys(synced_container_id, user_id)
                        except Exception:
                            pass
                    raise

            try:
                if new_password:
                    connection.execute(
                        """
                        UPDATE users
                        SET
                            username = ?,
                            real_name = ?,
                            role = ?,
                            status = ?,
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
                            user_status,
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
                            status = ?,
                            max_ssh_keys_per_user = ?,
                            max_join_keys_per_request = ?,
                            max_containers_per_user = ?
                        WHERE id = ?
                        """,
                        (
                            username,
                            real_name,
                            role,
                            user_status,
                            payload.max_ssh_keys_per_user,
                            payload.max_join_keys_per_request,
                            payload.max_containers_per_user,
                            user_id,
                        ),
                    )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                if status_changed and user_status == "disabled":
                    for container_id in active_container_ids:
                        try:
                            sync_container_user_authorized_keys(container_id, user_id)
                        except Exception:
                            pass
                if "users.username" in str(exc):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在") from exc
                raise
            except Exception as exc:
                if status_changed and user_status == "disabled":
                    for container_id in active_container_ids:
                        try:
                            sync_container_user_authorized_keys(container_id, user_id)
                        except Exception:
                            pass
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="用户更新失败") from exc

            if status_changed:
                if user_status == "disabled":
                    for container_id in offline_container_ids:
                        enqueue_pending_container_user_sync(container_id, user_id)
                elif user_status == "active":
                    for container_id in active_container_ids:
                        try:
                            sync_container_user_authorized_keys(container_id, user_id)
                        except Exception:
                            enqueue_pending_container_user_sync(container_id, user_id)
                    for container_id in offline_container_ids:
                        enqueue_pending_container_user_sync(container_id, user_id)

        updated = connection.execute(
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
            (user_id,),
        ).fetchone()
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


@router.get("/api/admin/containers")
def list_admin_containers(request: Request) -> dict:
    require_admin_user(request)
    return {"items": fetch_admin_containers()}


@router.get("/api/admin/containers/{container_id}/runtime")
def get_admin_container_runtime(container_id: int, request: Request) -> dict:
    require_admin_user(request)
    return fetch_container_runtime_payload(container_id)


@router.post("/api/admin/containers")
def create_admin_container(payload: AdminContainerCreatePayload, request: Request) -> dict:
    require_admin_user(request, require_csrf=True)

    name = payload.name.strip()
    host = payload.host.strip()
    root_password = normalize_optional_text(payload.root_password) or ""
    container_status = validate_container_status(payload.status)
    validate_ssh_root_login(host, payload.ssh_port, root_password)
    hardware_info = inspect_ssh_container_hardware(host, payload.ssh_port, root_password)

    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO containers (
                    name,
                    host,
                    ssh_port,
                    root_password,
                    max_users,
                    gpu_model,
                    gpu_memory,
                    gpu_count,
                    cpu_cores,
                    memory_size,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    host,
                    payload.ssh_port,
                    root_password,
                    payload.max_users,
                    hardware_info["gpu_model"],
                    hardware_info["gpu_memory"],
                    hardware_info["gpu_count"],
                    hardware_info["cpu_cores"],
                    hardware_info["memory_size"],
                    container_status,
                ),
            )
            container_id = cursor.lastrowid
            upsert_container_runtime_system(connection, int(container_id))
            connection.commit()
    except sqlite3.IntegrityError as exc:
        if "containers.name" in str(exc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="服务器名称已存在") from exc
        raise

    collect_container_runtime_now(int(container_id))
    with get_connection() as connection:
        item = connection.execute(
            """
            SELECT
                id,
                name,
                host,
                ssh_port,
                CASE WHEN COALESCE(root_password, '') = '' THEN 0 ELSE 1 END AS has_root_password,
                max_users,
                gpu_model,
                gpu_memory,
                gpu_count,
                cpu_cores,
                memory_size,
                status
            FROM containers
            WHERE id = ?
            """,
            (container_id,),
        ).fetchone()

    return {"ok": True, "item": dict(item), "message": "服务器已创建"}


@router.put("/api/admin/containers/{container_id}")
def update_admin_container(container_id: int, payload: AdminContainerUpdatePayload, request: Request) -> dict:
    require_admin_user(request, require_csrf=True)

    name = payload.name.strip()
    host = payload.host.strip()
    root_password = normalize_optional_text(payload.root_password)
    container_status = validate_container_status(payload.status)

    with get_connection() as connection:
        existing = connection.execute(
            """
            SELECT id, host, ssh_port, root_password
            FROM containers
            WHERE id = ?
            """,
            (container_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="服务器不存在")

        effective_root_password = root_password or str(existing["root_password"] or "").strip()
        validate_ssh_root_login(host, payload.ssh_port, effective_root_password)
        hardware_info = inspect_ssh_container_hardware(host, payload.ssh_port, effective_root_password)

        try:
            connection.execute(
                """
                UPDATE containers
                SET
                    name = ?,
                    host = ?,
                    ssh_port = ?,
                    root_password = COALESCE(NULLIF(?, ''), root_password),
                    max_users = ?,
                    gpu_model = ?,
                    gpu_memory = ?,
                    gpu_count = ?,
                    cpu_cores = ?,
                    memory_size = ?,
                    status = ?
                WHERE id = ?
                """,
                (
                    name,
                    host,
                    payload.ssh_port,
                    root_password,
                    payload.max_users,
                    hardware_info["gpu_model"],
                    hardware_info["gpu_memory"],
                    hardware_info["gpu_count"],
                    hardware_info["cpu_cores"],
                    hardware_info["memory_size"],
                    container_status,
                    container_id,
                ),
            )
            upsert_container_runtime_system(connection, container_id)
            connection.commit()
        except sqlite3.IntegrityError as exc:
            if "containers.name" in str(exc):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="服务器名称已存在") from exc
            raise

    collect_container_runtime_now(int(container_id))
    with get_connection() as connection:
        item = connection.execute(
            """
            SELECT
                id,
                name,
                host,
                ssh_port,
                CASE WHEN COALESCE(root_password, '') = '' THEN 0 ELSE 1 END AS has_root_password,
                max_users,
                gpu_model,
                gpu_memory,
                gpu_count,
                cpu_cores,
                memory_size,
                status
            FROM containers
            WHERE id = ?
            """,
            (container_id,),
        ).fetchone()
    return {"ok": True, "item": dict(item), "message": "服务器已更新"}


@router.delete("/api/admin/containers/{container_id}")
def delete_admin_container(container_id: int, request: Request) -> dict:
    require_admin_user(request, require_csrf=True)

    with get_connection() as connection:
        existing = connection.execute("SELECT id FROM containers WHERE id = ?", (container_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="服务器不存在")

        connection.execute("DELETE FROM ssh_key_container_bindings WHERE container_id = ?", (container_id,))
        connection.execute("DELETE FROM container_runtime_processes WHERE container_id = ?", (container_id,))
        connection.execute("DELETE FROM container_runtime_gpus WHERE container_id = ?", (container_id,))
        connection.execute("DELETE FROM container_runtime_system WHERE container_id = ?", (container_id,))
        connection.execute("DELETE FROM containers WHERE id = ?", (container_id,))
        connection.commit()
    return {"ok": True, "message": "服务器已删除"}
