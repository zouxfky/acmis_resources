import logging
import re
import threading
import time
from concurrent.futures import ALL_COMPLETED, ThreadPoolExecutor, wait
from typing import Optional

from backend.core.config import (
    RUNTIME_COLLECT_TOTAL_TIMEOUT_SECONDS,
    RUNTIME_MONITOR_ENABLED,
    RUNTIME_MONITOR_INTERVAL_SECONDS,
    RUNTIME_MONITOR_MAX_WORKERS,
    RUNTIME_MONITOR_OFFLINE_INTERVAL_SECONDS,
    RUNTIME_SSH_COMMAND_TIMEOUT_SECONDS,
)
from backend.core.db import begin_immediate, get_connection
from backend.core.helpers import clamp_percent, parse_size_to_g
from backend.features.container_ssh_access import (
    acquire_container_user_sync_lock,
    sync_container_user_authorized_keys,
)
from backend.features.runtime import (
    replace_container_runtime_gpus,
    replace_container_runtime_processes,
    upsert_container_runtime_system,
)

try:
    import paramiko
except ImportError:  # pragma: no cover - depends on local environment
    paramiko = None


LOGGER = logging.getLogger(__name__)
_INFLIGHT_IDS: set[int] = set()
_INFLIGHT_LOCK = threading.Lock()
_FAILURE_COUNTS: dict[int, int] = {}
_FAILURE_COUNTS_LOCK = threading.Lock()
_MAX_CONSECUTIVE_FAILURES_BEFORE_OFFLINE = 3
_RUNTIME_NOTICE_KEYS: set[tuple[int, str, str]] = set()
_RUNTIME_NOTICE_LOCK = threading.Lock()
_LAST_OFFLINE_COLLECT_AT: dict[int, float] = {}
_LAST_OFFLINE_COLLECT_AT_LOCK = threading.Lock()

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


def enqueue_pending_container_user_sync(container_id: int, user_id: int) -> None:
    with get_connection() as connection:
        begin_immediate(connection)
        connection.execute(
            """
            INSERT INTO pending_container_user_syncs (container_id, user_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(container_id, user_id) DO UPDATE SET
                updated_at = CURRENT_TIMESTAMP
            """,
            (container_id, user_id),
        )
        connection.commit()


def fetch_pending_container_user_sync_ids(container_id: int) -> list[int]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT user_id
            FROM pending_container_user_syncs
            WHERE container_id = ?
            ORDER BY updated_at ASC, user_id ASC
            """,
            (container_id,),
        ).fetchall()
    return [int(row["user_id"]) for row in rows]


def delete_pending_container_user_sync(container_id: int, user_id: int) -> None:
    with get_connection() as connection:
        begin_immediate(connection)
        connection.execute(
            """
            DELETE FROM pending_container_user_syncs
            WHERE container_id = ? AND user_id = ?
            """,
            (container_id, user_id),
        )
        connection.commit()


def process_pending_container_user_syncs(container_id: int) -> None:
    pending_user_ids = fetch_pending_container_user_sync_ids(container_id)
    if not pending_user_ids:
        return

    for user_id in pending_user_ids:
        try:
            with acquire_container_user_sync_lock(container_id, user_id):
                sync_container_user_authorized_keys(container_id, user_id)
            delete_pending_container_user_sync(container_id, user_id)
        except Exception:
            LOGGER.exception(
                "pending container ssh sync failed for container=%s user=%s",
                container_id,
                user_id,
            )


def prune_runtime_monitor_failure_counts(active_container_ids: set[int]) -> None:
    with _FAILURE_COUNTS_LOCK:
        stale_ids = [container_id for container_id in _FAILURE_COUNTS if container_id not in active_container_ids]
        for container_id in stale_ids:
            _FAILURE_COUNTS.pop(container_id, None)
    with _LAST_OFFLINE_COLLECT_AT_LOCK:
        stale_ids = [container_id for container_id in _LAST_OFFLINE_COLLECT_AT if container_id not in active_container_ids]
        for container_id in stale_ids:
            _LAST_OFFLINE_COLLECT_AT.pop(container_id, None)


def update_container_monitor_status(
    container_id: int,
    target_status: str,
    allowed_current_statuses: tuple[str, ...],
) -> None:
    placeholders = ",".join("?" for _ in allowed_current_statuses)
    params: list[object] = [target_status, container_id, *allowed_current_statuses]
    with get_connection() as connection:
        begin_immediate(connection)
        connection.execute(
            f"""
            UPDATE containers
            SET status = ?
            WHERE id = ?
              AND status IN ({placeholders})
            """,
            params,
        )
        connection.commit()


def mark_runtime_collect_success(container_id: int) -> None:
    with _FAILURE_COUNTS_LOCK:
        _FAILURE_COUNTS.pop(container_id, None)
    with _LAST_OFFLINE_COLLECT_AT_LOCK:
        _LAST_OFFLINE_COLLECT_AT.pop(container_id, None)
    update_container_monitor_status(container_id, "active", ("offline",))


def mark_runtime_collect_failure(container_id: int, container_name: str) -> None:
    with _FAILURE_COUNTS_LOCK:
        next_failure_count = _FAILURE_COUNTS.get(container_id, 0) + 1
        _FAILURE_COUNTS[container_id] = next_failure_count

    if next_failure_count < _MAX_CONSECUTIVE_FAILURES_BEFORE_OFFLINE:
        return

    LOGGER.warning(
        "runtime monitor marked container %s(%s) offline after %s consecutive failures",
        container_name,
        container_id,
        next_failure_count,
    )
    update_container_monitor_status(container_id, "offline", ("active",))


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


def should_collect_container_now(container_row: dict, now: float) -> bool:
    if str(container_row.get("status")) != "offline":
        return True

    container_id = int(container_row["id"])
    with _LAST_OFFLINE_COLLECT_AT_LOCK:
        last_collected_at = _LAST_OFFLINE_COLLECT_AT.get(container_id, 0.0)
        if now - last_collected_at < RUNTIME_MONITOR_OFFLINE_INTERVAL_SECONDS:
            return False
        _LAST_OFFLINE_COLLECT_AT[container_id] = now
    return True


def _normalize_runtime_error_text(exc: Exception) -> str:
    return str(exc).strip() or exc.__class__.__name__


def _is_missing_command_error(error_text: str) -> bool:
    lowered_error = error_text.lower()
    return any(
        token in lowered_error
        for token in ("command not found", "not found", "未找到命令")
    )


def _log_runtime_component_failure(component: str, container_name: str, container_id: int, exc: Exception) -> None:
    error_text = _normalize_runtime_error_text(exc)
    if _is_missing_command_error(error_text):
        notice_key = (container_id, component, error_text)
        with _RUNTIME_NOTICE_LOCK:
            if notice_key in _RUNTIME_NOTICE_KEYS:
                return
            _RUNTIME_NOTICE_KEYS.add(notice_key)
        LOGGER.warning(
            "%s runtime command unavailable for container %s(%s): %s",
            component,
            container_name,
            container_id,
            error_text,
        )
        return

    LOGGER.warning(
        "%s runtime collect failed for container %s(%s): %s",
        component,
        container_name,
        container_id,
        error_text,
    )


def exec_ssh_command(client, command: str, timeout: int, allowed_exit_codes: Optional[set[int]] = None) -> str:
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


class RuntimeMonitorService:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not RUNTIME_MONITOR_ENABLED:
            LOGGER.info("runtime monitor disabled by configuration")
            return
        if paramiko is None:
            LOGGER.warning("paramiko is not installed, runtime monitor will not start")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="acmis-runtime-monitor", daemon=True)
        self._thread.start()
        LOGGER.info(
            "runtime monitor started: interval=%ss offline_interval=%ss max_workers=%s",
            RUNTIME_MONITOR_INTERVAL_SECONDS,
            RUNTIME_MONITOR_OFFLINE_INTERVAL_SECONDS,
            RUNTIME_MONITOR_MAX_WORKERS,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            started_at = time.time()
            try:
                self.collect_once()
            except Exception:  # pragma: no cover - background safety net
                LOGGER.exception("runtime monitor round failed")

            elapsed = time.time() - started_at
            wait_seconds = max(0, RUNTIME_MONITOR_INTERVAL_SECONDS - elapsed)
            if self._stop_event.wait(wait_seconds):
                break

    def collect_once(self) -> None:
        container_rows = fetch_runtime_container_rows()
        if not container_rows:
            prune_runtime_monitor_failure_counts(set())
            return
        prune_runtime_monitor_failure_counts({int(row["id"]) for row in container_rows})
        now = time.time()
        container_rows = [row for row in container_rows if should_collect_container_now(row, now)]
        if not container_rows:
            return

        executor = ThreadPoolExecutor(max_workers=max(1, RUNTIME_MONITOR_MAX_WORKERS))
        future_map = {executor.submit(self._collect_container, row): row for row in container_rows}
        try:
            done, not_done = wait(
                future_map.keys(),
                timeout=RUNTIME_COLLECT_TOTAL_TIMEOUT_SECONDS,
                return_when=ALL_COMPLETED,
            )

            for future in done:
                try:
                    future.result()
                except Exception:
                    LOGGER.exception("runtime monitor worker failed")

            if not_done:
                timeout_container_labels = [
                    f'{future_map[future]["name"]}({future_map[future]["id"]})'
                    for future in not_done
                ]
                LOGGER.warning(
                    "runtime monitor round timed out after %ss, unfinished containers: %s",
                    RUNTIME_COLLECT_TOTAL_TIMEOUT_SECONDS,
                    ", ".join(timeout_container_labels),
                )
                for future in not_done:
                    future.cancel()
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _collect_container(self, container_row: dict) -> None:
        collect_container_runtime_row(container_row)


def collect_container_runtime_now(container_id: int) -> bool:
    if paramiko is None:
        return False
    container_row = fetch_runtime_container_row(container_id)
    if not container_row or container_row.get("status") not in {"active", "offline"}:
        return False
    return collect_container_runtime_row(container_row)


def collect_container_runtime_row(container_row: dict) -> bool:
    container_id = int(container_row["id"])
    container_name = str(container_row["name"])
    with _INFLIGHT_LOCK:
        if container_id in _INFLIGHT_IDS:
            return False
        _INFLIGHT_IDS.add(container_id)

    try:
        collection_state = _collect_container_runtime_inner(container_row)
        if collection_state == "success":
            mark_runtime_collect_success(container_id)
            process_pending_container_user_syncs(container_id)
            return True
        if collection_state == "connect_failure":
            mark_runtime_collect_failure(container_id, container_name)
        return False
    finally:
        with _INFLIGHT_LOCK:
            _INFLIGHT_IDS.discard(container_id)

def _collect_container_runtime_inner(container_row: dict) -> str:
    host = str(container_row["host"]).strip()
    ssh_port = int(container_row["ssh_port"])
    root_password = str(container_row["root_password"] or "").strip()
    container_id = int(container_row["id"])
    container_name = str(container_row["name"])

    if not host or not root_password:
        LOGGER.warning(
            "skip runtime monitor for container %s(%s): missing host or root password",
            container_name,
            container_id,
        )
        return "connect_failure"

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=host,
            port=ssh_port,
            username="root",
            password=root_password,
            timeout=RUNTIME_SSH_COMMAND_TIMEOUT_SECONDS,
            banner_timeout=RUNTIME_SSH_COMMAND_TIMEOUT_SECONDS,
            auth_timeout=RUNTIME_SSH_COMMAND_TIMEOUT_SECONDS,
            look_for_keys=False,
            allow_agent=False,
        )
        system_payload = build_empty_system_payload()
        gpu_rows: list[dict] = []
        process_rows: list[dict] = []

        try:
            gpu_output = exec_ssh_command(client, GPU_COMMAND, RUNTIME_SSH_COMMAND_TIMEOUT_SECONDS)
            gpu_rows = parse_gpu_output(gpu_output, timestamp)
            system_payload["gpu_available"] = True
        except Exception as exc:
            _log_runtime_component_failure("gpu", container_name, container_id, exc)

        cpu_output = None
        try:
            cpu_output = exec_ssh_command(client, CPU_COMMAND, RUNTIME_SSH_COMMAND_TIMEOUT_SECONDS)
            system_payload["cpu_available"] = True
        except Exception as exc:
            _log_runtime_component_failure("cpu", container_name, container_id, exc)

        memory_output = None
        try:
            memory_output = exec_ssh_command(client, MEMORY_COMMAND, RUNTIME_SSH_COMMAND_TIMEOUT_SECONDS)
            system_payload["memory_available"] = True
        except Exception as exc:
            _log_runtime_component_failure("memory", container_name, container_id, exc)

        if cpu_output or memory_output:
            parsed_system_payload = parse_system_output(cpu_output or "", memory_output or "")
            system_payload.update(parsed_system_payload)

        try:
            lsof_output = exec_ssh_command(
                client,
                LSOF_COMMAND,
                RUNTIME_SSH_COMMAND_TIMEOUT_SECONDS,
                allowed_exit_codes={0, 1},
            )
            lsof_rows = parse_lsof_output(lsof_output)
            ps_output = ""
            ps_command = build_ps_command(lsof_rows)
            if ps_command:
                ps_output = exec_ssh_command(client, ps_command, RUNTIME_SSH_COMMAND_TIMEOUT_SECONDS)
            user_id_map = fetch_user_id_map()
            process_rows = merge_process_rows(lsof_rows, parse_ps_output(ps_output), timestamp, user_id_map)
            system_payload["processes_available"] = True
        except Exception as exc:
            _log_runtime_component_failure("process", container_name, container_id, exc)

        save_runtime_snapshot(container_id, system_payload, gpu_rows, process_rows, timestamp)
        return "success"
    except Exception as exc:
        LOGGER.warning(
            "runtime monitor connect failed for container %s(%s): %s",
            container_name,
            container_id,
            _normalize_runtime_error_text(exc),
        )
        return "connect_failure"
    finally:
        client.close()
