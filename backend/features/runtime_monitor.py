import logging
import threading
import time
from concurrent.futures import ALL_COMPLETED, ThreadPoolExecutor, wait
from typing import Optional

from backend.core.config import (
    RUNTIME_COLLECT_TOTAL_TIMEOUT_SECONDS,
    RUNTIME_MONITOR_ENABLED,
    RUNTIME_MONITOR_INTERVAL_SECONDS,
    RUNTIME_MONITOR_MAX_WORKERS,
    SSH_CONNECT_TIMEOUT_SECONDS,
    RUNTIME_SSH_COMMAND_TIMEOUT_SECONDS,
)
from backend.core.db import begin_immediate, get_connection
from backend.features.container_ssh_access import (
    acquire_container_user_sync_lock,
    fetch_container_joined_user_ids,
    sync_container_user_authorized_keys,
)
from backend.features.runtime_collectors import (
    CPU_COMMAND,
    GPU_COMMAND,
    MEMORY_COMMAND,
    build_authorized_user_process_command,
    build_empty_system_payload,
    build_process_rows,
    build_runtime_timestamp,
    exec_ssh_command,
    fetch_container_joined_user_map,
    fetch_runtime_container_row,
    fetch_runtime_container_rows,
    filter_suspected_gpu_processes,
    parse_gpu_output,
    parse_process_scan_output,
    parse_system_output,
    save_runtime_snapshot,
    should_run_process_scan,
)

try:
    import paramiko
except ImportError:  # pragma: no cover - depends on local environment
    paramiko = None


LOGGER = logging.getLogger(__name__)
_INFLIGHT_IDS: set[int] = set()
_INFLIGHT_LOCK = threading.Lock()
_RUNTIME_NOTICE_KEYS: set[tuple[int, str, str]] = set()
_RUNTIME_NOTICE_LOCK = threading.Lock()


def sync_container_full_user_access(container_id: int) -> None:
    for user_id in fetch_container_joined_user_ids(container_id):
        try:
            with acquire_container_user_sync_lock(container_id, user_id):
                sync_container_user_authorized_keys(container_id, user_id)
        except Exception:
            LOGGER.exception(
                "container full ssh sync failed for container=%s user=%s",
                container_id,
                user_id,
            )


def update_container_monitor_status(
    container_id: int,
    target_status: str,
    allowed_current_statuses: tuple[str, ...],
) -> bool:
    placeholders = ",".join("?" for _ in allowed_current_statuses)
    params: list[object] = [target_status, container_id, *allowed_current_statuses]
    with get_connection() as connection:
        begin_immediate(connection)
        cursor = connection.execute(
            f"""
            UPDATE containers
            SET status = ?
            WHERE id = ?
              AND status IN ({placeholders})
            """,
            params,
        )
        connection.commit()
    return int(cursor.rowcount or 0) > 0


def mark_runtime_collect_success(container_id: int) -> None:
    update_container_monitor_status(container_id, "active", ("offline",))


def mark_runtime_collect_failure(container_id: int, container_name: str) -> None:
    LOGGER.warning(
        "runtime monitor marked container %s(%s) offline after two failed connect attempts in the same round",
        container_name,
        container_id,
    )
    update_container_monitor_status(container_id, "offline", ("active",))


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
            "runtime monitor started: interval=%ss max_workers=%s",
            RUNTIME_MONITOR_INTERVAL_SECONDS,
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
            return

        joined_user_map = fetch_container_joined_user_map([int(row["id"]) for row in container_rows])
        executor = ThreadPoolExecutor(max_workers=max(1, RUNTIME_MONITOR_MAX_WORKERS))
        future_map = {
            executor.submit(self._collect_container, row, joined_user_map.get(int(row["id"]), [])): row
            for row in container_rows
        }
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

    def _collect_container(self, container_row: dict, joined_users: list[dict]) -> None:
        collect_container_runtime_row(container_row, joined_users)


def collect_container_runtime_now(container_id: int) -> bool:
    if paramiko is None:
        return False
    container_row = fetch_runtime_container_row(container_id)
    if not container_row or container_row.get("status") not in {"active", "offline"}:
        return False
    joined_user_map = fetch_container_joined_user_map([container_id])
    return collect_container_runtime_row(container_row, joined_user_map.get(container_id, []))


def collect_container_runtime_row(container_row: dict, joined_users: Optional[list[dict]] = None) -> bool:
    container_id = int(container_row["id"])
    container_name = str(container_row["name"])
    was_offline = str(container_row.get("status")) == "offline"
    if joined_users is None:
        joined_user_map = fetch_container_joined_user_map([container_id])
        joined_users = joined_user_map.get(container_id, [])
    with _INFLIGHT_LOCK:
        if container_id in _INFLIGHT_IDS:
            return False
        _INFLIGHT_IDS.add(container_id)

    try:
        collection_state = _collect_container_runtime_inner(container_row, joined_users)
        if collection_state == "success":
            mark_runtime_collect_success(container_id)
            if was_offline:
                sync_container_full_user_access(container_id)
            return True
        if collection_state == "connect_failure":
            if was_offline:
                return False

            LOGGER.warning(
                "runtime monitor connect failed for container %s(%s), retrying once in the same round",
                container_name,
                container_id,
            )
            retry_state = _collect_container_runtime_inner(container_row, joined_users)
            if retry_state == "success":
                mark_runtime_collect_success(container_id)
                sync_container_full_user_access(container_id)
                return True

            mark_runtime_collect_failure(container_id, container_name)
        return False
    finally:
        with _INFLIGHT_LOCK:
            _INFLIGHT_IDS.discard(container_id)


def _collect_container_runtime_inner(container_row: dict, joined_users: list[dict]) -> str:
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

    timestamp = build_runtime_timestamp()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=host,
            port=ssh_port,
            username="root",
            password=root_password,
            timeout=SSH_CONNECT_TIMEOUT_SECONDS,
            banner_timeout=SSH_CONNECT_TIMEOUT_SECONDS,
            auth_timeout=SSH_CONNECT_TIMEOUT_SECONDS,
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

        if system_payload["gpu_available"]:
            try:
                if should_run_process_scan(joined_users, gpu_rows):
                    process_command = build_authorized_user_process_command(
                        [str(item.get("username") or "").strip() for item in joined_users]
                    )
                    if process_command:
                        process_output = exec_ssh_command(
                            client,
                            process_command,
                            RUNTIME_SSH_COMMAND_TIMEOUT_SECONDS,
                            allowed_exit_codes={0, 1},
                        )
                        process_items = parse_process_scan_output(process_output)
                        filtered_process_items = filter_suspected_gpu_processes(process_items)
                        process_rows = build_process_rows(filtered_process_items, joined_users, timestamp)
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
