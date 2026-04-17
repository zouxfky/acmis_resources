import base64
import logging
import shlex
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from fastapi import HTTPException, status

from backend.core.config import CONTAINER_USER_HOME_ROOT, SSH_LOGIN_TIMEOUT_SECONDS, SSH_SYNC_COMMAND_TIMEOUT_SECONDS
from backend.core.db import get_connection
from backend.core.helpers import validate_linux_username

try:
    import paramiko
except ImportError:  # pragma: no cover - depends on local environment
    paramiko = None


LOGGER = logging.getLogger(__name__)
_SYNC_LOCKS: dict[tuple[int, int], threading.Lock] = {}
_SYNC_LOCKS_GUARD = threading.Lock()


@dataclass
class ContainerUserSyncPayload:
    container_id: int
    user_id: int
    linux_username: str
    host: str
    ssh_port: int
    root_password: str
    public_keys: list[str]


def fetch_container_user_sync_payload(container_id: int, user_id: int) -> ContainerUserSyncPayload:
    with get_connection() as connection:
        user_row = connection.execute(
            """
            SELECT id, username, status
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

    linux_username = validate_linux_username(str(user_row["username"]))
    host = str(container_row["host"] or "").strip()
    root_password = str(container_row["root_password"] or "").strip()
    if not host or not root_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="容器缺少可用的 SSH Root 连接信息")

    public_keys = normalize_public_keys([str(row["public_key"]) for row in key_rows])
    if str(user_row["status"]) != "active":
        public_keys = []

    return ContainerUserSyncPayload(
        container_id=int(container_row["id"]),
        user_id=int(user_row["id"]),
        linux_username=linux_username,
        host=host,
        ssh_port=int(container_row["ssh_port"]),
        root_password=root_password,
        public_keys=public_keys,
    )


def normalize_public_key(public_key: str) -> str:
    normalized = public_key.strip()
    return normalized


def normalize_public_keys(public_keys: list[str]) -> list[str]:
    normalized_items = [normalize_public_key(item) for item in public_keys]
    normalized_items = [item for item in normalized_items if item]
    return list(dict.fromkeys(normalized_items))


def render_authorized_keys_text(public_keys: list[str]) -> str:
    if not public_keys:
        return ""
    return "\n".join(public_keys) + "\n"


def _build_sync_command(linux_username: str, authorized_keys_text: str) -> str:
    payload_b64 = base64.b64encode(authorized_keys_text.encode("utf-8")).decode("ascii")
    quoted_username = shlex.quote(linux_username)
    quoted_home_root = shlex.quote(CONTAINER_USER_HOME_ROOT)
    quoted_payload = shlex.quote(payload_b64)
    return f"""
set -e
USERNAME={quoted_username}
HOME_ROOT={quoted_home_root}
PAYLOAD_B64={quoted_payload}

if getent passwd "$USERNAME" >/dev/null; then
  HOME_DIR="$(getent passwd "$USERNAME" | cut -d: -f6)"
else
  install -d "$HOME_ROOT"
  HOME_DIR="$HOME_ROOT/$USERNAME"
  useradd -m -d "$HOME_DIR" -s /bin/bash "$USERNAME"
fi

USER_GROUP="$(id -gn "$USERNAME")"
# Keep permissions scoped to the user's home directory.
install -d -m 700 -o "$USERNAME" -g "$USER_GROUP" "$HOME_DIR"
install -d -m 700 -o "$USERNAME" -g "$USER_GROUP" "$HOME_DIR/.ssh"

AUTH_FILE="$HOME_DIR/.ssh/authorized_keys"
LOCK_FILE="$HOME_DIR/.ssh/.authorized_keys.lock"
TMP_FILE="$(mktemp "$HOME_DIR/.ssh/authorized_keys.tmp.XXXXXX")"
cleanup_tmp_file() {{
  if [ -n "$TMP_FILE" ] && [ -e "$TMP_FILE" ]; then
    rm -f "$TMP_FILE"
  fi
}}
trap cleanup_tmp_file EXIT INT TERM HUP

(
  flock -x 9
  touch "$AUTH_FILE"
  chown "$USERNAME:$USER_GROUP" "$AUTH_FILE"
  chmod 600 "$AUTH_FILE"

  if [ -n "$PAYLOAD_B64" ]; then
    printf '%s' "$PAYLOAD_B64" | base64 -d > "$TMP_FILE"
  else
    : > "$TMP_FILE"
  fi

  chown "$USERNAME:$USER_GROUP" "$TMP_FILE"
  chmod 600 "$TMP_FILE"
  mv "$TMP_FILE" "$AUTH_FILE"
) 9>"$LOCK_FILE"
trap - EXIT INT TERM HUP
""".strip()


def _exec_ssh_command(client: "paramiko.SSHClient", command: str) -> str:
    stdin, stdout, stderr = client.exec_command(command, timeout=SSH_SYNC_COMMAND_TIMEOUT_SECONDS)
    del stdin
    output = stdout.read().decode("utf-8", errors="replace")
    error_output = stderr.read().decode("utf-8", errors="replace").strip()
    exit_code = stdout.channel.recv_exit_status()
    if exit_code != 0:
        raise RuntimeError(error_output or "远端 SSH 授权同步命令执行失败")
    return output


def sync_container_user_authorized_keys(
    container_id: int,
    user_id: int,
    public_keys_override: list[str] | None = None,
) -> None:
    if paramiko is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="后端未安装 paramiko，无法同步容器 SSH 授权",
        )

    payload = fetch_container_user_sync_payload(container_id, user_id)
    public_keys = payload.public_keys if public_keys_override is None else normalize_public_keys(public_keys_override)
    command = _build_sync_command(payload.linux_username, render_authorized_keys_text(public_keys))

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=payload.host,
            port=payload.ssh_port,
            username="root",
            password=payload.root_password,
            timeout=SSH_LOGIN_TIMEOUT_SECONDS,
            banner_timeout=SSH_LOGIN_TIMEOUT_SECONDS,
            auth_timeout=SSH_LOGIN_TIMEOUT_SECONDS,
            look_for_keys=False,
            allow_agent=False,
        )
        _exec_ssh_command(client, command)
    except HTTPException:
        raise
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


def _get_sync_lock(key: tuple[int, int]) -> threading.Lock:
    with _SYNC_LOCKS_GUARD:
        lock = _SYNC_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _SYNC_LOCKS[key] = lock
        return lock


@contextmanager
def acquire_container_user_sync_lock(container_id: int, user_id: int) -> Iterator[None]:
    lock = _get_sync_lock((int(container_id), int(user_id)))
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


@contextmanager
def acquire_container_user_sync_locks(lock_items: list[tuple[int, int]]) -> Iterator[None]:
    normalized_items = sorted({(int(container_id), int(user_id)) for container_id, user_id in lock_items})
    locks = [_get_sync_lock(item) for item in normalized_items]
    for lock in locks:
        lock.acquire()
    try:
        yield
    finally:
        for lock in reversed(locks):
            lock.release()


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
