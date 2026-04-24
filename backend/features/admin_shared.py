import sqlite3

from backend.core.db import get_connection
from backend.features.container_port_mappings import fetch_container_port_mapping_map
from backend.features.runtime import (
    build_runtime_payload_for_container,
    fetch_runtime_snapshot_maps,
)


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
                u.linux_uid,
                u.linux_gid,
                u.max_ssh_keys_per_user,
                u.max_join_keys_per_request,
                u.max_containers_per_user,
                COUNT(DISTINCT ub.ssh_key_id) AS ssh_key_count,
                COUNT(DISTINCT scb.container_id) AS access_count
            FROM users u
            LEFT JOIN user_ssh_key_bindings ub ON ub.user_id = u.id
            LEFT JOIN ssh_key_container_bindings scb ON scb.ssh_key_id = ub.ssh_key_id
            GROUP BY
                u.id, u.username, u.real_name, u.role, u.linux_uid, u.linux_gid,
                u.max_ssh_keys_per_user, u.max_join_keys_per_request, u.max_containers_per_user
            ORDER BY u.id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_admin_container_detail(connection: sqlite3.Connection, container_id: int):
    row = connection.execute(
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
    if not row:
        return None
    port_mapping_map = fetch_container_port_mapping_map(connection, [container_id])
    item = dict(row)
    item["port_mappings"] = port_mapping_map.get(container_id, [])
    return item


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
        port_mapping_map = fetch_container_port_mapping_map(connection, [int(row["id"]) for row in rows])

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
                "port_mappings": port_mapping_map.get(int(row["id"]), []),
            }
        )
        items.append(item)
    return items
