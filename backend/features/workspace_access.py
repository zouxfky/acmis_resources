import logging

from fastapi import HTTPException, status

from backend.core.config import (
    DEFAULT_MAX_CONTAINERS_PER_USER,
    DEFAULT_MAX_JOIN_KEYS_PER_REQUEST,
)
from backend.core.db import begin_immediate, get_connection
from backend.features.container_ssh_access import (
    acquire_container_user_sync_lock,
    acquire_container_user_sync_locks,
    fetch_user_container_public_keys,
    sync_container_user_authorized_keys,
)
from backend.features.runtime_monitor import enqueue_pending_container_user_sync


LOGGER = logging.getLogger(__name__)


def join_workspace_container_access(user_id: int, container_id: int, ssh_key_ids: list[int]) -> dict:
    normalized_key_ids = sorted({int(item) for item in ssh_key_ids})
    if not normalized_key_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少选择一把 SSH 公钥")

    with acquire_container_user_sync_lock(container_id, user_id):
        inserted_key_ids: list[int] = []

        with get_connection() as connection:
            begin_immediate(connection)
            quota_row = connection.execute(
                """
                SELECT max_join_keys_per_request, max_containers_per_user
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
            max_join_keys_per_request = (
                int(quota_row["max_join_keys_per_request"]) if quota_row else DEFAULT_MAX_JOIN_KEYS_PER_REQUEST
            )
            max_containers_per_user = (
                int(quota_row["max_containers_per_user"]) if quota_row else DEFAULT_MAX_CONTAINERS_PER_USER
            )
            if len(normalized_key_ids) > max_join_keys_per_request:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"单次最多只能选择 {max_join_keys_per_request} 把 SSH 公钥",
                )

            container = connection.execute(
                """
                SELECT id, status, max_users
                FROM containers
                WHERE id = ?
                """,
                (container_id,),
            ).fetchone()
            if not container:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="容器不存在")
            if container["status"] != "active":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前容器不可加入")

            owned_key_rows = connection.execute(
                f"""
                SELECT ssh_key_id
                FROM user_ssh_key_bindings
                WHERE user_id = ? AND ssh_key_id IN ({",".join("?" for _ in normalized_key_ids)})
                """,
                (user_id, *normalized_key_ids),
            ).fetchall()
            owned_key_ids = {int(row["ssh_key_id"]) for row in owned_key_rows}
            if len(owned_key_ids) != len(normalized_key_ids):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="所选 SSH 公钥不属于当前用户")

            existing_selected_rows = connection.execute(
                f"""
                SELECT scb.ssh_key_id
                FROM ssh_key_container_bindings scb
                JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
                WHERE ub.user_id = ? AND scb.container_id = ? AND scb.ssh_key_id IN ({",".join("?" for _ in normalized_key_ids)})
                """,
                (user_id, container_id, *normalized_key_ids),
            ).fetchall()
            existing_selected_ids = {int(row["ssh_key_id"]) for row in existing_selected_rows}
            inserted_key_ids = [item for item in normalized_key_ids if item not in existing_selected_ids]
            if not inserted_key_ids:
                connection.rollback()
                return {"sync_pending": False}

            existing_membership = connection.execute(
                """
                SELECT 1
                FROM ssh_key_container_bindings scb
                JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
                WHERE ub.user_id = ? AND scb.container_id = ?
                LIMIT 1
                """,
                (user_id, container_id),
            ).fetchone()
            if not existing_membership:
                joined_container_count = connection.execute(
                    """
                    SELECT COUNT(DISTINCT scb.container_id)
                    FROM ssh_key_container_bindings scb
                    JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
                    WHERE ub.user_id = ?
                    """,
                    (user_id,),
                ).fetchone()[0]
                if joined_container_count >= max_containers_per_user:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"当前账户最多只能加入 {max_containers_per_user} 台容器",
                    )

                active_user_count = connection.execute(
                    """
                    SELECT COUNT(DISTINCT ub.user_id)
                    FROM ssh_key_container_bindings scb
                    JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
                    WHERE scb.container_id = ?
                    """,
                    (container_id,),
                ).fetchone()[0]
                if active_user_count >= container["max_users"]:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前容器已达到最大接入人数")

            connection.executemany(
                """
                INSERT OR IGNORE INTO ssh_key_container_bindings (ssh_key_id, container_id)
                VALUES (?, ?)
                """,
                [(ssh_key_id, container_id) for ssh_key_id in inserted_key_ids],
            )
            connection.commit()

        try:
            sync_container_user_authorized_keys(container_id, user_id)
        except Exception as exc:
            enqueue_pending_container_user_sync(container_id, user_id)
            LOGGER.warning(
                "join access saved but container sync deferred for container=%s user=%s: %s",
                container_id,
                user_id,
                exc,
            )
            return {"sync_pending": True}

    return {"sync_pending": False}


def leave_workspace_container_access(user_id: int, container_id: int, ssh_key_ids: list[int]) -> bool:
    with acquire_container_user_sync_lock(container_id, user_id):
        leaving_key_ids: list[int] = []
        remaining_public_keys: list[str] = []

        with get_connection() as connection:
            begin_immediate(connection)
            container = connection.execute(
                "SELECT id, status FROM containers WHERE id = ?",
                (container_id,),
            ).fetchone()
            if not container:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="容器不存在")

            current_key_rows = connection.execute(
                """
                SELECT scb.ssh_key_id
                FROM ssh_key_container_bindings scb
                JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
                WHERE ub.user_id = ? AND scb.container_id = ?
                """,
                (user_id, container_id),
            ).fetchall()
            current_key_ids = {int(row["ssh_key_id"]) for row in current_key_rows}
            if not current_key_ids:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前容器没有可退出的 SSH 公钥绑定")

            if ssh_key_ids:
                leaving_key_ids = sorted({int(item) for item in ssh_key_ids})
                if not set(leaving_key_ids).issubset(current_key_ids):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="存在不属于当前容器授权的 SSH 公钥",
                    )
            else:
                leaving_key_ids = sorted(current_key_ids)

            if not leaving_key_ids:
                connection.rollback()
                return False

            remaining_key_rows = connection.execute(
                f"""
                SELECT DISTINCT k.public_key
                FROM ssh_public_keys k
                JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = k.id
                JOIN ssh_key_container_bindings scb ON scb.ssh_key_id = k.id
                WHERE ub.user_id = ? AND scb.container_id = ? AND scb.ssh_key_id NOT IN ({",".join("?" for _ in leaving_key_ids)})
                ORDER BY k.id ASC
                """,
                (user_id, container_id, *leaving_key_ids),
            ).fetchall()
            remaining_public_keys = [str(row["public_key"]) for row in remaining_key_rows]

        if container["status"] == "active":
            sync_container_user_authorized_keys(container_id, user_id, remaining_public_keys)

        try:
            with get_connection() as connection:
                begin_immediate(connection)
                connection.executemany(
                    """
                    DELETE FROM ssh_key_container_bindings
                    WHERE ssh_key_id = ? AND container_id = ?
                    """,
                    [(ssh_key_id, container_id) for ssh_key_id in leaving_key_ids],
                )
                connection.commit()
        except Exception as exc:
            if container["status"] == "active":
                _resync_from_database(container_id, user_id)
            raise _build_database_failure("退出", exc) from exc

        if container["status"] != "active":
            enqueue_pending_container_user_sync(container_id, user_id)

    return True


def delete_workspace_ssh_key_and_sync(user_id: int, ssh_key_id: int) -> dict:
    with get_connection() as connection:
        begin_immediate(connection)
        binding = connection.execute(
            """
            SELECT ssh_key_id
            FROM user_ssh_key_bindings
            WHERE user_id = ? AND ssh_key_id = ?
            """,
            (user_id, ssh_key_id),
        ).fetchone()
        if not binding:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSH 公钥不存在")

        key_row = connection.execute(
            """
            SELECT id, key_name, fingerprint, public_key
            FROM ssh_public_keys
            WHERE id = ?
            """,
            (ssh_key_id,),
        ).fetchone()
        affected_container_rows = connection.execute(
            """
            SELECT DISTINCT scb.container_id, c.status
            FROM ssh_key_container_bindings scb
            JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
            JOIN containers c ON c.id = scb.container_id
            WHERE ub.user_id = ? AND scb.ssh_key_id = ?
            ORDER BY scb.container_id ASC
            """,
            (user_id, ssh_key_id),
        ).fetchall()
        affected_container_ids = [int(row["container_id"]) for row in affected_container_rows]
        connection.rollback()

    lock_items = [(container_id, user_id) for container_id in affected_container_ids]
    with acquire_container_user_sync_locks(lock_items):
        active_container_ids = [
            int(row["container_id"]) for row in affected_container_rows if row["status"] == "active"
        ]
        offline_container_ids = [
            int(row["container_id"]) for row in affected_container_rows if row["status"] != "active"
        ]
        active_container_public_keys: dict[int, list[str]] = {
            container_id: [
                public_key
                for public_key in fetch_user_container_public_keys(user_id, container_id)
                if public_key != str(key_row["public_key"])
            ]
            for container_id in active_container_ids
        }
        synced_active_container_ids: list[int] = []
        try:
            for container_id in active_container_ids:
                sync_container_user_authorized_keys(container_id, user_id, active_container_public_keys[container_id])
                synced_active_container_ids.append(container_id)
        except Exception:
            for synced_container_id in synced_active_container_ids:
                _resync_from_database(synced_container_id, user_id)
            raise

        try:
            with get_connection() as connection:
                begin_immediate(connection)
                binding = connection.execute(
                    """
                    SELECT ssh_key_id
                    FROM user_ssh_key_bindings
                    WHERE user_id = ? AND ssh_key_id = ?
                    """,
                    (user_id, ssh_key_id),
                ).fetchone()
                if not binding:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSH 公钥不存在")

                connection.execute("DELETE FROM ssh_key_container_bindings WHERE ssh_key_id = ?", (ssh_key_id,))
                connection.execute(
                    "DELETE FROM user_ssh_key_bindings WHERE user_id = ? AND ssh_key_id = ?",
                    (user_id, ssh_key_id),
                )
                connection.execute("DELETE FROM ssh_public_keys WHERE id = ?", (ssh_key_id,))
                connection.commit()
        except Exception as exc:
            for container_id in active_container_ids:
                _resync_from_database(container_id, user_id)
            raise _build_database_failure("删除 SSH 公钥", exc) from exc

        for container_id in offline_container_ids:
            enqueue_pending_container_user_sync(container_id, user_id)

    return {"affected_container_ids": affected_container_ids}


def _resync_from_database(container_id: int, user_id: int) -> None:
    try:
        sync_container_user_authorized_keys(container_id, user_id)
    except Exception:
        LOGGER.exception("database state resync failed for container=%s user=%s", container_id, user_id)


def _build_database_failure(action_name: str, exc: Exception) -> HTTPException:
    detail = exc.detail if isinstance(exc, HTTPException) else str(exc) or f"{action_name}失败"
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"{action_name}时数据库更新失败。{detail}",
    )
