import sqlite3

from fastapi import APIRouter, HTTPException, Request, status

from backend.core.db import get_connection
from backend.core.helpers import (
    inspect_ssh_container_hardware,
    normalize_optional_text,
    validate_container_status,
)
from backend.core.security import require_admin_user
from backend.features.admin_shared import fetch_admin_container_detail, fetch_admin_containers
from backend.features.runtime import (
    fetch_container_runtime_payload,
    upsert_container_runtime_system,
)
from backend.features.runtime_monitor import collect_container_runtime_now
from backend.schemas import AdminContainerCreatePayload, AdminContainerUpdatePayload


router = APIRouter()


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
        item = fetch_admin_container_detail(connection, int(container_id))

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
        item = fetch_admin_container_detail(connection, int(container_id))
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
