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
LSOF_COMMAND = r"lsof /dev/nvidia* 2>/dev/null | awk 'NR>1 {print $1, $2, $3}' | sort -u"


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


def parse_lsof_output(output: str) -> list[dict]:
    items: list[dict] = []
    seen_pids: set[int] = set()
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        command_name, pid_text, linux_username = parts
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if pid in seen_pids:
            continue
        seen_pids.add(pid)
        items.append(
            {
                "command_name": command_name,
                "pid": pid,
                "linux_username": linux_username.strip(),
            }
        )
    return items


def build_ps_command(pid_items: list[dict]) -> Optional[str]:
    if not pid_items:
        return None
    pid_list = ",".join(str(item["pid"]) for item in pid_items)
    return f"ps -p {pid_list} -o pid=,user=,args="


def parse_ps_output(output: str) -> dict[int, dict]:
    process_map: dict[int, dict] = {}
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
        process_map[pid] = {
            "pid": pid,
            "linux_username": parts[1].strip(),
            "process_name": parts[2].strip(),
        }
    return process_map


def merge_process_rows(
    lsof_rows: list[dict],
    ps_map: dict[int, dict],
    timestamp: str,
    user_id_map: dict[str, int],
) -> list[dict]:
    process_rows: list[dict] = []
    for item in lsof_rows:
        process_detail = ps_map.get(item["pid"], {})
        linux_username = process_detail.get("linux_username") or item["linux_username"]
        process_name = process_detail.get("process_name") or item["command_name"]
        process_rows.append(
            {
                "user_id": user_id_map.get(linux_username),
                "linux_username": linux_username,
                "pid": item["pid"],
                "process_name": process_name,
                "updated_at": timestamp,
            }
        )
    return process_rows


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


def fetch_user_id_map() -> dict[str, int]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, username
            FROM users
            ORDER BY id ASC
            """
        ).fetchall()
    return {str(row["username"]): int(row["id"]) for row in rows}


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
