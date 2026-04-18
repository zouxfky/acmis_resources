import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status

from backend.core.config import (
    DEFAULT_MAX_SSH_KEYS_PER_USER,
)
from backend.core.db import get_connection
from backend.core.helpers import compute_ssh_fingerprint
from backend.core.security import require_authenticated_user
from backend.features.runtime import (
    build_runtime_payload_for_container,
    fetch_container_runtime_payload,
    fetch_runtime_snapshot_maps,
)
from backend.features.workspace_access import (
    delete_workspace_ssh_key_and_sync,
    join_workspace_container_access,
    leave_workspace_container_access,
)
from backend.schemas import WorkspaceContainerBindingPayload, WorkspaceSshKeyCreatePayload


router = APIRouter()


def serialize_workspace_ssh_key_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "key_name": row["key_name"],
        "fingerprint": row["fingerprint"],
        "public_key": row["public_key"],
    }


def fetch_workspace_ssh_keys(user_id: int) -> list[dict]:
    with get_connection() as connection:
        ssh_key_rows = connection.execute(
            """
            SELECT k.id, k.key_name, k.fingerprint, k.public_key
            FROM ssh_public_keys k
            JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = k.id
            WHERE ub.user_id = ?
            ORDER BY k.id DESC
            """,
            (user_id,),
        ).fetchall()
    return [serialize_workspace_ssh_key_row(row) for row in ssh_key_rows]


def fetch_workspace_containers(user_id: int, container_ids: Optional[list[int]] = None) -> list[dict]:
    if container_ids is not None and len(container_ids) == 0:
        return []

    with get_connection() as connection:
        container_filter_sql = ""
        container_params: list[object] = []
        if container_ids:
            placeholders = ",".join("?" for _ in container_ids)
            container_filter_sql = f"WHERE c.id IN ({placeholders})"
            container_params.extend(container_ids)

        container_rows = connection.execute(
            f"""
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
            {container_filter_sql}
            GROUP BY
                c.id, c.name, c.host, c.ssh_port, c.root_password, c.max_users,
                c.gpu_model, c.gpu_memory, c.gpu_count, c.cpu_cores, c.memory_size, c.status
            ORDER BY c.id ASC
            """,
            container_params,
        ).fetchall()
        system_map, gpu_runtime_map, process_runtime_map = fetch_runtime_snapshot_maps(connection, container_ids)

        joined_binding_sql = """
            SELECT scb.container_id, scb.ssh_key_id
            FROM ssh_key_container_bindings scb
            JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
            WHERE ub.user_id = ?
        """
        joined_binding_params: list[object] = [user_id]
        if container_ids:
            placeholders = ",".join("?" for _ in container_ids)
            joined_binding_sql += f" AND scb.container_id IN ({placeholders})"
            joined_binding_params.extend(container_ids)
        joined_binding_sql += " ORDER BY scb.container_id ASC, scb.ssh_key_id ASC"
        joined_binding_rows = connection.execute(joined_binding_sql, joined_binding_params).fetchall()

        connected_user_sql = """
            SELECT
                scb.container_id,
                COALESCE(u.real_name, u.username) AS user_name
            FROM ssh_key_container_bindings scb
            JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
            JOIN users u ON u.id = ub.user_id
        """
        connected_user_params: list[object] = []
        if container_ids:
            placeholders = ",".join("?" for _ in container_ids)
            connected_user_sql += f" WHERE scb.container_id IN ({placeholders})"
            connected_user_params.extend(container_ids)
        connected_user_sql += """
            GROUP BY scb.container_id, u.id, COALESCE(u.real_name, u.username)
            ORDER BY scb.container_id ASC, u.id ASC
        """
        connected_user_rows = connection.execute(connected_user_sql, connected_user_params).fetchall()

        process_user_rows = connection.execute(
            """
            SELECT username, COALESCE(real_name, username) AS display_name
            FROM users
            ORDER BY id ASC
            """
        ).fetchall()

    joined_key_map: dict[int, list[int]] = {}
    for row in joined_binding_rows:
        joined_key_map.setdefault(row["container_id"], []).append(row["ssh_key_id"])

    connected_user_map: dict[int, list[str]] = {}
    for row in connected_user_rows:
        connected_user_map.setdefault(row["container_id"], []).append(row["user_name"])

    process_user_display_map = {
        str(row["username"]): str(row["display_name"])
        for row in process_user_rows
    }

    process_map: dict[int, list[str]] = {}
    process_detail_map: dict[int, list[dict]] = {}
    for container_id, process_rows in process_runtime_map.items():
        for row in process_rows:
            process_owner = process_user_display_map.get(str(row["linux_username"]), str(row["linux_username"]))
            process_map.setdefault(container_id, []).append(f'{process_owner} / {row["process_name"]}')
            process_detail_map.setdefault(container_id, []).append(
                {
                    "pid": row["pid"],
                    "process_user": process_owner,
                    "process_name": row["process_name"],
                    "gpu_memory_mb": 0,
                    "cpu_percent": 0,
                    "memory_percent": 0,
                }
            )

    items = []
    for row in container_rows:
        runtime_payload = build_runtime_payload_for_container(
            row,
            system_map.get(row["id"]),
            gpu_runtime_map.get(row["id"], []),
        )
        items.append(
            {
                "id": row["id"],
                "name": row["name"],
                "host": row["host"],
                "ssh_port": row["ssh_port"],
                "max_users": row["max_users"],
                "gpu_model": row["gpu_model"],
                "gpu_memory": row["gpu_memory"],
                "gpu_count": row["gpu_count"],
                "cpu_cores": row["cpu_cores"],
                "memory_size": row["memory_size"],
                "connected_users": connected_user_map.get(row["id"], []),
                "gpu_usage_percent": runtime_payload["gpu_usage_percent"],
                "gpu_usage_summary": runtime_payload["gpu_usage_summary"],
                "cpu_usage_percent": runtime_payload["cpu_usage_percent"],
                "cpu_usage_summary": runtime_payload["cpu_usage_summary"],
                "memory_usage_percent": runtime_payload["memory_usage_percent"],
                "memory_usage_summary": runtime_payload["memory_usage_summary"],
                "cpu_runtime_available": runtime_payload["cpu_runtime_available"],
                "memory_runtime_available": runtime_payload["memory_runtime_available"],
                "gpu_runtime_available": runtime_payload["gpu_runtime_available"],
                "process_runtime_available": runtime_payload["process_runtime_available"],
                "runtime_updated_at": runtime_payload["runtime_updated_at"],
                "runtime_gpus": runtime_payload["runtime_gpus"],
                "gpu_processes": process_map.get(row["id"], []),
                "runtime_processes": process_detail_map.get(row["id"], []),
                "status": row["status"],
                "active_user_count": row["active_user_count"],
                "joined_key_ids": joined_key_map.get(row["id"], []),
            }
        )
    return items


def fetch_workspace_container(user_id: int, container_id: int) -> dict:
    container_items = fetch_workspace_containers(user_id, [container_id])
    if not container_items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="容器不存在")
    return container_items[0]


def fetch_workspace_payload(user_id: int) -> dict:
    return {
        "ssh_keys": fetch_workspace_ssh_keys(user_id),
        "containers": fetch_workspace_containers(user_id),
    }


@router.get("/api/workspace")
def get_workspace(request: Request) -> dict:
    user = require_authenticated_user(request)
    return fetch_workspace_payload(user["id"])


@router.get("/api/workspace/containers/{container_id}/runtime")
def get_workspace_container_runtime(container_id: int, request: Request) -> dict:
    require_authenticated_user(request)
    return fetch_container_runtime_payload(container_id)


@router.post("/api/workspace/ssh-keys")
def create_workspace_ssh_key(payload: WorkspaceSshKeyCreatePayload, request: Request) -> dict:
    user = require_authenticated_user(request, require_csrf=True)
    key_name = payload.key_name.strip()
    public_key = payload.public_key.strip()

    if not public_key.startswith("ssh-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSH 公钥格式不正确，必须以 ssh- 开头",
        )

    fingerprint = compute_ssh_fingerprint(public_key)

    try:
        with get_connection() as connection:
            quota_row = connection.execute(
                """
                SELECT max_ssh_keys_per_user
                FROM users
                WHERE id = ?
                """,
                (user["id"],),
            ).fetchone()
            max_ssh_keys_per_user = (
                int(quota_row["max_ssh_keys_per_user"]) if quota_row else DEFAULT_MAX_SSH_KEYS_PER_USER
            )
            current_key_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM user_ssh_key_bindings
                WHERE user_id = ?
                """,
                (user["id"],),
            ).fetchone()[0]
            if current_key_count >= max_ssh_keys_per_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"当前账户最多只能保存 {max_ssh_keys_per_user} 把 SSH 公钥",
                )

            cursor = connection.execute(
                """
                INSERT INTO ssh_public_keys (key_name, fingerprint, public_key)
                VALUES (?, ?, ?)
                """,
                (key_name, fingerprint, public_key),
            )
            ssh_key_id = cursor.lastrowid
            connection.execute(
                """
                INSERT INTO user_ssh_key_bindings (user_id, ssh_key_id)
                VALUES (?, ?)
                """,
                (user["id"], ssh_key_id),
            )
            connection.commit()
    except sqlite3.IntegrityError as exc:
        if "ssh_public_keys.fingerprint" in str(exc) or "UNIQUE constraint failed: ssh_public_keys.fingerprint" in str(exc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="这把 SSH 公钥已经存在") from exc
        raise

    return {"ok": True, "message": "SSH 公钥已添加", "ssh_keys": fetch_workspace_ssh_keys(user["id"])}


@router.delete("/api/workspace/ssh-keys/{ssh_key_id}")
def delete_workspace_ssh_key(ssh_key_id: int, request: Request) -> dict:
    user = require_authenticated_user(request, require_csrf=True)
    result = delete_workspace_ssh_key_and_sync(user["id"], ssh_key_id)

    return {
        "ok": True,
        "message": "SSH 公钥已删除",
        "ssh_keys": fetch_workspace_ssh_keys(user["id"]),
        "containers": fetch_workspace_containers(user["id"], result["affected_container_ids"]),
    }


@router.post("/api/workspace/containers/{container_id}/join")
def join_workspace_container(
    container_id: int,
    payload: WorkspaceContainerBindingPayload,
    request: Request,
) -> dict:
    user = require_authenticated_user(request, require_csrf=True)
    join_workspace_container_access(user["id"], container_id, payload.ssh_key_ids)

    return {
        "ok": True,
        "message": "容器授权已更新",
        "container": fetch_workspace_container(user["id"], container_id),
    }


@router.post("/api/workspace/containers/{container_id}/leave")
def leave_workspace_container(
    container_id: int,
    payload: WorkspaceContainerBindingPayload,
    request: Request,
) -> dict:
    user = require_authenticated_user(request, require_csrf=True)
    leave_workspace_container_access(user["id"], container_id, payload.ssh_key_ids)

    return {"ok": True, "message": "容器授权已撤销", "container": fetch_workspace_container(user["id"], container_id)}
