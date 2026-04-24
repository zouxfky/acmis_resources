import os
import re
import time
from typing import Any, Optional

from backend.core.db import begin_immediate, get_connection
from backend.core.helpers import clamp_percent, parse_size_to_g
from backend.features.runtime import (
    replace_container_runtime_gpus,
    replace_container_runtime_processes,
    upsert_container_runtime_system,
)

GPU_COMMAND = (
    "nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu "
    "--format=csv,noheader,nounits"
)
CPU_COMMAND = "top -bn1 | head -n 5"
MEMORY_COMMAND = "free -b | awk 'NR==2 {print $2, $3}'"
PROCESS_SCAN_BASE_COMMAND = "ps -eww -o pid=,user=,args="
SAFE_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
PYTHON_INTERPRETER_PATTERN = re.compile(r"^python(?:\d+(?:\.\d+)*)?$")
TASK_TOKEN_PATTERN = re.compile(r"(^|\s)(train|serve|infer|eval)(\s|$)")
MODULE_MARKER_PATTERN = re.compile(r"(^|\s)-m(\s|$)")
TASK_KEYWORDS = (
    "accelerate",
    "api_server",
    "deepspeed",
    "generate",
    "inference",
    "jupyter",
    "lmdeploy",
    "sglang",
    "tensorboard",
    "tritonserver",
    "torchrun",
    "vllm",
)


def mib_to_g(value: float) -> float:
    return round(float(value) / 1024.0, 1)


def parse_gpu_output(output: str, timestamp: str) -> list[dict]:
    gpu_rows: list[dict] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [item.strip() for item in line.split(",")]
        if len(parts) < 5:
            continue
        try:
            gpu_index = int(parts[0])
            memory_total_mb = float(parts[2])
            memory_used_mb = float(parts[3])
            compute_percent = clamp_percent(float(parts[4]))
        except ValueError:
            continue

        memory_percent = (
            clamp_percent((memory_used_mb / memory_total_mb) * 100) if memory_total_mb > 0 else 0
        )
        gpu_rows.append(
            {
                "gpu_index": gpu_index,
                "memory_total_g": mib_to_g(memory_total_mb),
                "memory_used_g": mib_to_g(memory_used_mb),
                "memory_percent": memory_percent,
                "compute_percent": compute_percent,
                "updated_at": timestamp,
            }
        )
    return gpu_rows


def parse_system_output(cpu_output: str, memory_output: str) -> dict:
    cpu_percent = 0
    memory_used_g = 0.0
    memory_total_g = 0.0
    memory_percent = 0

    for raw_line in cpu_output.splitlines():
        line = raw_line.strip()
        if "%Cpu" in line and " id" in line:
            idle_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*id", line)
            if idle_match:
                cpu_percent = clamp_percent(100 - float(idle_match.group(1)))

    memory_parts = [item.strip() for item in re.split(r"[\s,]+", memory_output.strip()) if item.strip()]
    if len(memory_parts) >= 2:
        memory_total_g = parse_size_to_g(f"{memory_parts[0]}B")
        memory_used_g = parse_size_to_g(f"{memory_parts[1]}B")
        memory_percent = (
            clamp_percent((memory_used_g / memory_total_g) * 100) if memory_total_g > 0 else 0
        )

    return {
        "cpu_percent": cpu_percent,
        "memory_used_g": round(memory_used_g, 1),
        "memory_total_g": round(memory_total_g, 1),
        "memory_percent": memory_percent,
    }


def parse_process_scan_output(output: str) -> list[dict]:
    process_items: list[dict] = []
    seen_pids: set[int] = set()
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if pid in seen_pids:
            continue
        seen_pids.add(pid)
        process_items.append(
            {
                "pid": pid,
                "linux_username": parts[1].strip(),
                "process_name": parts[2].strip(),
            }
        )
    return process_items


def fetch_runtime_container_rows() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, name, host, ssh_port, root_password, gpu_count, gpu_memory, status
            FROM containers
            WHERE status IN ('active', 'offline')
            ORDER BY id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_runtime_container_row(container_id: int) -> Optional[dict]:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, name, host, ssh_port, root_password, gpu_count, gpu_memory, status
            FROM containers
            WHERE id = ?
            """,
            (container_id,),
        ).fetchone()
    return dict(row) if row else None


def fetch_container_joined_user_map(container_ids: list[int]) -> dict[int, list[dict]]:
    if not container_ids:
        return {}

    placeholders = ",".join("?" for _ in container_ids)
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT DISTINCT scb.container_id, u.id AS user_id, u.username
            FROM ssh_key_container_bindings scb
            JOIN user_ssh_key_bindings ub ON ub.ssh_key_id = scb.ssh_key_id
            JOIN users u ON u.id = ub.user_id
            WHERE scb.container_id IN ({placeholders})
            ORDER BY scb.container_id ASC, u.id ASC
            """,
            container_ids,
        ).fetchall()

    joined_user_map: dict[int, list[dict]] = {}
    for row in rows:
        username = str(row["username"] or "").strip()
        if not username:
            continue
        joined_user_map.setdefault(int(row["container_id"]), []).append(
            {
                "user_id": int(row["user_id"]),
                "username": username,
            }
        )
    return joined_user_map


def should_run_process_scan(joined_users: list[dict], gpu_rows: list[dict]) -> bool:
    if not joined_users or not gpu_rows:
        return False
    return any(
        float(row.get("memory_used_g", 0)) > 0 or float(row.get("compute_percent", 0)) > 0
        for row in gpu_rows
    )


def build_authorized_user_process_command(usernames: list[str]) -> Optional[str]:
    normalized_usernames: list[str] = []
    seen_usernames: set[str] = set()

    for username in usernames:
        normalized_username = str(username or "").strip()
        if (
            not normalized_username
            or normalized_username in seen_usernames
            or not SAFE_USERNAME_PATTERN.fullmatch(normalized_username)
        ):
            continue
        seen_usernames.add(normalized_username)
        normalized_usernames.append(normalized_username)

    if not normalized_usernames:
        return None

    user_conditions = " || ".join(f'$2==\"{username}\"' for username in normalized_usernames)
    return f"{PROCESS_SCAN_BASE_COMMAND} | awk '{user_conditions} {{print}}'"


def filter_suspected_gpu_processes(process_items: list[dict]) -> list[dict]:
    filtered_items: list[dict] = []
    for item in process_items:
        process_name = str(item.get("process_name") or "").strip()
        if not process_name:
            continue

        command_token = process_name.split(None, 1)[0]
        command_name = os.path.basename(command_token).lower()
        process_name_lower = process_name.lower()

        has_task_keyword = any(keyword in process_name_lower for keyword in TASK_KEYWORDS)
        has_task_token = bool(TASK_TOKEN_PATTERN.search(process_name_lower))
        has_module_marker = bool(MODULE_MARKER_PATTERN.search(process_name_lower))
        has_python_script = ".py" in process_name_lower

        if PYTHON_INTERPRETER_PATTERN.fullmatch(command_name) or command_name == "ipython":
            if has_task_keyword or has_task_token or has_module_marker or has_python_script:
                filtered_items.append(item)
            continue

        if has_task_keyword or has_task_token:
            filtered_items.append(item)

    return filtered_items


def build_process_rows(process_items: list[dict], joined_users: list[dict], timestamp: str) -> list[dict]:
    user_id_map = {
        str(item["username"]): int(item["user_id"])
        for item in joined_users
        if item.get("username") and item.get("user_id") is not None
    }
    process_rows: list[dict] = []
    seen_pids: set[int] = set()

    for item in process_items:
        try:
            pid = int(item["pid"])
        except (TypeError, ValueError, KeyError):
            continue

        if pid in seen_pids:
            continue
        seen_pids.add(pid)

        linux_username = str(item.get("linux_username") or "").strip()
        process_name = str(item.get("process_name") or "").strip()
        if not linux_username or not process_name:
            continue

        process_rows.append(
            {
                "user_id": user_id_map.get(linux_username),
                "linux_username": linux_username,
                "pid": pid,
                "process_name": process_name,
                "updated_at": timestamp,
            }
        )

    return process_rows


def save_runtime_snapshot(
    container_id: int,
    system_payload: dict,
    gpu_rows: list[dict],
    process_rows: list[dict],
    timestamp: str,
) -> None:
    with get_connection() as connection:
        begin_immediate(connection)
        upsert_container_runtime_system(
            connection,
            container_id,
            cpu_percent=system_payload["cpu_percent"],
            memory_used_g=system_payload["memory_used_g"],
            memory_total_g=system_payload["memory_total_g"],
            memory_percent=system_payload["memory_percent"],
            cpu_available=system_payload["cpu_available"],
            memory_available=system_payload["memory_available"],
            gpu_available=system_payload["gpu_available"],
            processes_available=system_payload["processes_available"],
            updated_at=timestamp,
        )
        replace_container_runtime_gpus(connection, container_id, gpu_rows)
        replace_container_runtime_processes(connection, container_id, process_rows)
        connection.commit()


def build_empty_system_payload() -> dict:
    return {
        "cpu_percent": 0,
        "memory_used_g": 0.0,
        "memory_total_g": 0.0,
        "memory_percent": 0,
        "cpu_available": False,
        "memory_available": False,
        "gpu_available": False,
        "processes_available": False,
    }


def exec_ssh_command(
    client: Any,
    command: str,
    timeout: int,
    allowed_exit_codes: Optional[set[int]] = None,
) -> str:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    del stdin
    output = stdout.read().decode("utf-8", errors="replace")
    error_output = stderr.read().decode("utf-8", errors="replace").strip()
    exit_code = stdout.channel.recv_exit_status()
    if allowed_exit_codes and exit_code in allowed_exit_codes:
        return output
    if exit_code != 0:
        raise RuntimeError(error_output or f"远端命令执行失败: {command}")
    return output


def build_runtime_timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
