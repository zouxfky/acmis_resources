import logging
import sqlite3
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, status

from backend.core.db import begin_immediate, get_connection
from backend.core.helpers import validate_linux_username
from backend.features.container_ssh_client import (
    ContainerSSHConnectError,
    exec_ssh_command,
    open_root_client,
)
from backend.features.container_ssh_scripts import (
    build_sync_command,
    normalize_public_keys,
    render_authorized_keys_text,
)


LOGGER = logging.getLogger(__name__)


@dataclass
class ContainerUserSyncPayload:
    container_id: int
    user_id: int
    linux_username: str
    linux_uid: int
    linux_gid: int
    host: str
    ssh_port: int
    root_password: str
    public_keys: list[str]


def build_container_user_sync_payload(
    connection: sqlite3.Connection,
    container_id: int,
    user_id: int,
    public_keys_override: Optional[list[str]] = None,
) -> ContainerUserSyncPayload:
    user_row = connection.execute(
        """
        SELECT id, username, linux_uid, linux_gid
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()
    if not user_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    container_row = connection.execute(
        """
        SELECT id, host, ssh_port, root_password, status
        FROM containers
        WHERE id = ?
        """,
        (container_id,),
    ).fetchone()
    if not container_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="容器不存在")
    if container_row["status"] != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前容器不可同步 SSH 授权")

    if public_keys_override is None:
        key_rows = connection.execute(
            """
            SELECT DISTINCT k.public_key
            FROM ssh_public_keys k
            JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = k.id
            JOIN ssh_key_container_bindings scb ON scb.ssh_key_id = k.id
            WHERE ub.user_id = ? AND scb.container_id = ?
            ORDER BY k.id ASC
            """,
            (user_id, container_id),
        ).fetchall()
        public_keys = normalize_public_keys([str(row["public_key"]) for row in key_rows])
    else:
        public_keys = normalize_public_keys(public_keys_override)

    linux_username = validate_linux_username(str(user_row["username"]))
    host = str(container_row["host"] or "").strip()
    root_password = str(container_row["root_password"] or "").strip()
    if not host or not root_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="容器缺少可用的 SSH Root 连接信息")

    return ContainerUserSyncPayload(
        container_id=int(container_row["id"]),
        user_id=int(user_row["id"]),
        linux_username=linux_username,
        linux_uid=int(user_row["linux_uid"]),
        linux_gid=int(user_row["linux_gid"]),
        host=host,
        ssh_port=int(container_row["ssh_port"]),
        root_password=root_password,
        public_keys=public_keys,
    )


def fetch_container_user_sync_payload(container_id: int, user_id: int) -> ContainerUserSyncPayload:
    with get_connection() as connection:
        return build_container_user_sync_payload(connection, container_id, user_id)


def mark_container_offline(container_id: int) -> None:
    with get_connection() as connection:
        begin_immediate(connection)
        connection.execute(
            """
            UPDATE containers
            SET status = 'offline'
            WHERE id = ? AND status = 'active'
            """,
            (container_id,),
        )
        connection.commit()


def ensure_container_ssh_available(container_id: int, retry_attempts: int = 2) -> None:
    with get_connection() as connection:
        container_row = connection.execute(
            """
            SELECT id, host, ssh_port, root_password, status
            FROM containers
            WHERE id = ?
            """,
            (container_id,),
        ).fetchone()
    if not container_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="容器不存在")
    if container_row["status"] != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前容器不可连接")

    host = str(container_row["host"] or "").strip()
    root_password = str(container_row["root_password"] or "").strip()
    if not host or not root_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="容器缺少可用的 SSH Root 连接信息")

    last_error: Optional[Exception] = None
    for _ in range(max(1, retry_attempts)):
        try:
            client = open_root_client(host, int(container_row["ssh_port"]), root_password)
        except ContainerSSHConnectError as exc:
            last_error = exc
            continue
        else:
            client.close()
            return

    mark_container_offline(int(container_row["id"]))
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"容器当前无法连接，已标记离线：{host}:{int(container_row['ssh_port'])}",
    ) from last_error


def sync_container_user_authorized_keys(
    container_id: int,
    user_id: int,
    public_keys_override: Optional[list[str]] = None,
) -> None:
    payload = fetch_container_user_sync_payload(container_id, user_id)
    public_keys = payload.public_keys if public_keys_override is None else normalize_public_keys(public_keys_override)
    sync_container_user_authorized_keys_payload(payload, public_keys)


def sync_container_user_authorized_keys_payload(
    payload: ContainerUserSyncPayload,
    public_keys_override: Optional[list[str]] = None,
) -> None:
    public_keys = payload.public_keys if public_keys_override is None else normalize_public_keys(public_keys_override)
    command = build_sync_command(
        payload.linux_username,
        payload.linux_uid,
        payload.linux_gid,
        render_authorized_keys_text(public_keys),
    )

    try:
        client = open_root_client(payload.host, payload.ssh_port, payload.root_password)
    except ContainerSSHConnectError as exc:
        mark_container_offline(payload.container_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"容器当前无法连接：{payload.host}:{payload.ssh_port}",
        ) from exc

    try:
        exec_ssh_command(client, command)
    except HTTPException:
        raise
    except ContainerSSHConnectError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"容器当前无法连接：{payload.host}:{payload.ssh_port}",
        ) from exc
    except Exception as exc:
        LOGGER.exception(
            "container ssh key sync failed for container=%s user=%s",
            payload.container_id,
            payload.user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"容器内 SSH 授权同步失败：{payload.host}:{payload.ssh_port}",
        ) from exc
    finally:
        client.close()


def fetch_user_container_public_keys(user_id: int, container_id: int) -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT k.public_key
            FROM ssh_public_keys k
            JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = k.id
            JOIN ssh_key_container_bindings scb ON scb.ssh_key_id = k.id
            WHERE ub.user_id = ? AND scb.container_id = ?
            ORDER BY k.id ASC
            """,
            (user_id, container_id),
        ).fetchall()
    return normalize_public_keys([str(row["public_key"]) for row in rows])


def fetch_user_joined_container_rows(user_id: int) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT c.id, c.status
            FROM containers c
            JOIN ssh_key_container_bindings scb ON scb.container_id = c.id
            JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
            WHERE ub.user_id = ?
            ORDER BY c.id ASC
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_container_joined_user_ids(container_id: int) -> list[int]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT ub.user_id
            FROM ssh_key_container_bindings scb
            JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
            WHERE scb.container_id = ?
            ORDER BY ub.user_id ASC
            """,
            (container_id,),
        ).fetchall()
    return [int(row["user_id"]) for row in rows]
