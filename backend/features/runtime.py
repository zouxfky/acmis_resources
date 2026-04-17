import sqlite3
from typing import Optional

from fastapi import HTTPException, status

from backend.core.db import get_connection
from backend.core.helpers import (
    build_cpu_usage_summary,
    build_gpu_usage_summary,
    build_memory_usage_summary,
    clamp_percent,
)


def create_runtime_schema_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS container_runtime_system (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            container_id INTEGER NOT NULL UNIQUE,
            cpu_percent INTEGER NOT NULL DEFAULT 0,
            memory_used_g REAL NOT NULL DEFAULT 0,
            memory_total_g REAL NOT NULL DEFAULT 0,
            memory_percent INTEGER NOT NULL DEFAULT 0,
            cpu_available INTEGER NOT NULL DEFAULT 1,
            memory_available INTEGER NOT NULL DEFAULT 1,
            gpu_available INTEGER NOT NULL DEFAULT 1,
            processes_available INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS container_runtime_gpus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            container_id INTEGER NOT NULL,
            gpu_index INTEGER NOT NULL,
            memory_total_g REAL NOT NULL DEFAULT 0,
            memory_used_g REAL NOT NULL DEFAULT 0,
            memory_percent INTEGER NOT NULL DEFAULT 0,
            compute_percent INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(container_id, gpu_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS container_runtime_processes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            container_id INTEGER NOT NULL,
            user_id INTEGER,
            linux_username TEXT NOT NULL,
            pid INTEGER NOT NULL,
            process_name TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(container_id, pid)
        )
        """
    )
    _ensure_runtime_system_columns(
        connection,
        {
            "cpu_available": "INTEGER NOT NULL DEFAULT 1",
            "memory_available": "INTEGER NOT NULL DEFAULT 1",
            "gpu_available": "INTEGER NOT NULL DEFAULT 1",
            "processes_available": "INTEGER NOT NULL DEFAULT 1",
        },
    )


def _ensure_runtime_system_columns(connection: sqlite3.Connection, columns: dict[str, str]) -> None:
    existing_columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(container_runtime_system)").fetchall()
    }
    for column_name, column_sql in columns.items():
        if column_name in existing_columns:
            continue
        connection.execute(f"ALTER TABLE container_runtime_system ADD COLUMN {column_name} {column_sql}")


def upsert_container_runtime_system(
    connection: sqlite3.Connection,
    container_id: int,
    cpu_percent: int = 0,
    memory_used_g: float = 0.0,
    memory_total_g: float = 0.0,
    memory_percent: int = 0,
    cpu_available: bool = True,
    memory_available: bool = True,
    gpu_available: bool = True,
    processes_available: bool = True,
    updated_at: Optional[str] = None,
) -> None:
    if updated_at:
        connection.execute(
            """
            INSERT INTO container_runtime_system (
                container_id,
                cpu_percent,
                memory_used_g,
                memory_total_g,
                memory_percent,
                cpu_available,
                memory_available,
                gpu_available,
                processes_available,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(container_id) DO UPDATE SET
                cpu_percent = excluded.cpu_percent,
                memory_used_g = excluded.memory_used_g,
                memory_total_g = excluded.memory_total_g,
                memory_percent = excluded.memory_percent,
                cpu_available = excluded.cpu_available,
                memory_available = excluded.memory_available,
                gpu_available = excluded.gpu_available,
                processes_available = excluded.processes_available,
                updated_at = excluded.updated_at
            """,
            (
                container_id,
                clamp_percent(cpu_percent),
                round(memory_used_g, 1),
                round(memory_total_g, 1),
                clamp_percent(memory_percent),
                1 if cpu_available else 0,
                1 if memory_available else 0,
                1 if gpu_available else 0,
                1 if processes_available else 0,
                updated_at,
            ),
        )
        return

    connection.execute(
        """
        INSERT INTO container_runtime_system (
            container_id,
            cpu_percent,
            memory_used_g,
            memory_total_g,
            memory_percent,
            cpu_available,
            memory_available,
            gpu_available,
            processes_available,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(container_id) DO UPDATE SET
            cpu_percent = excluded.cpu_percent,
            memory_used_g = excluded.memory_used_g,
            memory_total_g = excluded.memory_total_g,
            memory_percent = excluded.memory_percent,
            cpu_available = excluded.cpu_available,
            memory_available = excluded.memory_available,
            gpu_available = excluded.gpu_available,
            processes_available = excluded.processes_available,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            container_id,
            clamp_percent(cpu_percent),
            round(memory_used_g, 1),
            round(memory_total_g, 1),
            clamp_percent(memory_percent),
            1 if cpu_available else 0,
            1 if memory_available else 0,
            1 if gpu_available else 0,
            1 if processes_available else 0,
        ),
    )


def replace_container_runtime_gpus(connection: sqlite3.Connection, container_id: int, gpu_rows: list[dict]) -> None:
    connection.execute("DELETE FROM container_runtime_gpus WHERE container_id = ?", (container_id,))
    if not gpu_rows:
        return
    connection.executemany(
        """
        INSERT INTO container_runtime_gpus (
            container_id,
            gpu_index,
            memory_total_g,
            memory_used_g,
            memory_percent,
            compute_percent,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                container_id,
                int(row["gpu_index"]),
                round(float(row["memory_total_g"]), 1),
                round(float(row["memory_used_g"]), 1),
                clamp_percent(row["memory_percent"]),
                clamp_percent(row["compute_percent"]),
                row["updated_at"],
            )
            for row in gpu_rows
        ],
    )


def replace_container_runtime_processes(
    connection: sqlite3.Connection,
    container_id: int,
    process_rows: list[dict],
) -> None:
    connection.execute("DELETE FROM container_runtime_processes WHERE container_id = ?", (container_id,))
    if not process_rows:
        return
    connection.executemany(
        """
        INSERT INTO container_runtime_processes (
            container_id,
            user_id,
            linux_username,
            pid,
            process_name,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                container_id,
                row.get("user_id"),
                str(row["linux_username"]),
                int(row["pid"]),
                str(row["process_name"]),
                row["updated_at"],
            )
            for row in process_rows
        ],
    )


def fetch_runtime_snapshot_maps(
    connection: sqlite3.Connection,
    container_ids: Optional[list[int]] = None,
) -> tuple[dict[int, sqlite3.Row], dict[int, list[sqlite3.Row]], dict[int, list[sqlite3.Row]]]:
    system_sql = """
        SELECT
            container_id,
            cpu_percent,
            memory_used_g,
            memory_total_g,
            memory_percent,
            cpu_available,
            memory_available,
            gpu_available,
            processes_available,
            updated_at
        FROM container_runtime_system
    """
    system_params: list[object] = []
    if container_ids:
        placeholders = ",".join("?" for _ in container_ids)
        system_sql += f" WHERE container_id IN ({placeholders})"
        system_params.extend(container_ids)
    system_rows = connection.execute(system_sql, system_params).fetchall()

    gpu_sql = """
        SELECT container_id, gpu_index, memory_total_g, memory_used_g, memory_percent, compute_percent, updated_at
        FROM container_runtime_gpus
    """
    gpu_params: list[object] = []
    if container_ids:
        placeholders = ",".join("?" for _ in container_ids)
        gpu_sql += f" WHERE container_id IN ({placeholders})"
        gpu_params.extend(container_ids)
    gpu_sql += " ORDER BY container_id ASC, gpu_index ASC"
    gpu_rows = connection.execute(gpu_sql, gpu_params).fetchall()

    process_sql = """
        SELECT container_id, user_id, linux_username, pid, process_name, updated_at
        FROM container_runtime_processes
    """
    process_params: list[object] = []
    if container_ids:
        placeholders = ",".join("?" for _ in container_ids)
        process_sql += f" WHERE container_id IN ({placeholders})"
        process_params.extend(container_ids)
    process_sql += " ORDER BY container_id ASC, linux_username ASC, process_name ASC, pid ASC"
    process_rows = connection.execute(process_sql, process_params).fetchall()

    system_map = {row["container_id"]: row for row in system_rows}
    gpu_map: dict[int, list[sqlite3.Row]] = {}
    for row in gpu_rows:
        gpu_map.setdefault(row["container_id"], []).append(row)
    process_map: dict[int, list[sqlite3.Row]] = {}
    for row in process_rows:
        process_map.setdefault(row["container_id"], []).append(row)
    return system_map, gpu_map, process_map


def build_runtime_payload_for_container(
    container_row: sqlite3.Row,
    system_row: Optional[sqlite3.Row],
    gpu_rows: list[sqlite3.Row],
) -> dict:
    cpu_available = bool(system_row["cpu_available"]) if system_row and "cpu_available" in system_row.keys() else False
    memory_available = (
        bool(system_row["memory_available"]) if system_row and "memory_available" in system_row.keys() else False
    )
    gpu_available = bool(system_row["gpu_available"]) if system_row and "gpu_available" in system_row.keys() else False
    processes_available = (
        bool(system_row["processes_available"]) if system_row and "processes_available" in system_row.keys() else False
    )

    cpu_percent = int(system_row["cpu_percent"]) if system_row and cpu_available else None
    memory_used_g = float(system_row["memory_used_g"]) if system_row and memory_available else None
    memory_total_g = float(system_row["memory_total_g"]) if system_row and memory_available else None
    memory_percent = None
    if system_row and memory_available:
        memory_percent = int(system_row["memory_percent"])
    elif memory_available and memory_used_g is not None and memory_total_g and memory_total_g > 0:
        memory_percent = clamp_percent((memory_used_g / memory_total_g) * 100)

    total_gpu_memory_g = round(sum(float(row["memory_total_g"]) for row in gpu_rows), 1)
    used_gpu_memory_g = round(sum(float(row["memory_used_g"]) for row in gpu_rows), 1)
    gpu_compute_percent = None
    if gpu_available and gpu_rows:
        gpu_compute_percent = clamp_percent(sum(float(row["compute_percent"]) for row in gpu_rows) / len(gpu_rows))
    elif gpu_available:
        gpu_compute_percent = 0

    return {
        "gpu_usage_percent": gpu_compute_percent,
        "gpu_usage_summary": (
            build_gpu_usage_summary(gpu_compute_percent, used_gpu_memory_g, total_gpu_memory_g)
            if gpu_available and gpu_compute_percent is not None
            else None
        ),
        "cpu_usage_percent": cpu_percent,
        "cpu_usage_summary": (
            build_cpu_usage_summary(cpu_percent, int(container_row["cpu_cores"]))
            if cpu_available and cpu_percent is not None
            else None
        ),
        "memory_usage_percent": memory_percent,
        "memory_usage_summary": (
            build_memory_usage_summary(memory_percent, memory_used_g or 0.0, memory_total_g or 0.0)
            if memory_available and memory_percent is not None
            else None
        ),
        "cpu_runtime_available": cpu_available,
        "memory_runtime_available": memory_available,
        "gpu_runtime_available": gpu_available,
        "process_runtime_available": processes_available,
        "runtime_updated_at": (
            system_row["updated_at"]
            if system_row and system_row["updated_at"]
            else (gpu_rows[0]["updated_at"] if gpu_rows else None)
        ),
        "runtime_gpus": [dict(row) for row in gpu_rows],
    }


def fetch_container_runtime_payload(container_id: int) -> dict:
    with get_connection() as connection:
        container = connection.execute(
            """
            SELECT id, name, status, cpu_cores
            FROM containers
            WHERE id = ?
            """,
            (container_id,),
        ).fetchone()
        if not container:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="容器不存在")
        system_map, gpu_runtime_map, process_runtime_map = fetch_runtime_snapshot_maps(connection, [container_id])
        runtime_payload = build_runtime_payload_for_container(
            container,
            system_map.get(container_id),
            gpu_runtime_map.get(container_id, []),
        )
        connected_user_rows = connection.execute(
            """
            SELECT DISTINCT COALESCE(u.real_name, u.username) AS user_name
            FROM ssh_key_container_bindings scb
            JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
            JOIN users u ON u.id = ub.user_id
            WHERE scb.container_id = ?
            ORDER BY user_name ASC
            """,
            (container_id,),
        ).fetchall()

    return {
        "container": {"id": container["id"], "name": container["name"], "status": container["status"]},
        "metrics": {
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
            "updated_at": runtime_payload["runtime_updated_at"],
        },
        "gpus": runtime_payload["runtime_gpus"],
        "connected_users": [row["user_name"] for row in connected_user_rows],
        "processes": [
            {
                "pid": row["pid"],
                "process_user": row["linux_username"],
                "process_name": row["process_name"],
                "updated_at": row["updated_at"],
            }
            for row in process_runtime_map.get(container_id, [])
        ],
    }
