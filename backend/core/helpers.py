import base64
import hashlib
import os
import re
import sqlite3
import subprocess
from typing import Optional

from fastapi import HTTPException, status

from backend.core.config import SSH_LOGIN_TIMEOUT_SECONDS


LINUX_USERNAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


def validate_ssh_root_login(host: str, port: int, password: str) -> None:
    normalized_host = host.strip()
    if not normalized_host:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="主机地址不能为空",
        )
    normalized_password = password.strip()
    if not normalized_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="需要提供 Root 密码用于校验 SSH 登录",
        )

    command = [
        "sshpass",
        "-e",
        "ssh",
        "-T",
        "-p",
        str(port),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        "PreferredAuthentications=password",
        "-o",
        "PubkeyAuthentication=no",
        "-o",
        "NumberOfPasswordPrompts=1",
        "-o",
        f"ConnectTimeout={SSH_LOGIN_TIMEOUT_SECONDS}",
        f"root@{normalized_host}",
        "exit",
    ]
    ssh_env = os.environ.copy()
    ssh_env["SSHPASS"] = normalized_password
    try:
        result = subprocess.run(
            command,
            env=ssh_env,
            capture_output=True,
            text=True,
            timeout=SSH_LOGIN_TIMEOUT_SECONDS + 2,
            check=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="后端未安装 sshpass，无法校验服务器登录",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"连接 {normalized_host}:{port} 超时，无法完成 Root 登录校验",
        ) from exc

    if result.returncode == 0:
        return

    stderr_text = (result.stderr or "").strip()
    stdout_text = (result.stdout or "").strip()
    error_text = stderr_text or stdout_text
    lowered_error = error_text.lower()

    if "permission denied" in lowered_error:
        detail = f"{normalized_host}:{port} Root 密码错误，或服务器禁止密码登录"
    elif "connection refused" in lowered_error:
        detail = f"{normalized_host}:{port} 拒绝连接"
    elif "operation timed out" in lowered_error or "connection timed out" in lowered_error:
        detail = f"连接 {normalized_host}:{port} 超时，无法完成 Root 登录校验"
    elif "no route to host" in lowered_error:
        detail = f"无法到达 {normalized_host}:{port}"
    elif "could not resolve hostname" in lowered_error or "name or service not known" in lowered_error:
        detail = f"无法解析主机地址 {normalized_host}"
    elif "connection closed" in lowered_error or "kex_exchange_identification" in lowered_error:
        detail = f"{normalized_host}:{port} SSH 握手失败"
    else:
        detail = error_text or f"{normalized_host}:{port} Root 登录校验失败"

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=detail,
    )


def inspect_ssh_container_hardware(host: str, port: int, password: str) -> dict:
    normalized_host = host.strip()
    normalized_password = password.strip()
    if not normalized_host or not normalized_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="需要提供有效的主机地址和 Root 密码用于探测硬件信息",
        )

    try:
        import paramiko
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="后端未安装 paramiko，无法通过 SSH 探测硬件信息",
        ) from exc

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=normalized_host,
            port=port,
            username="root",
            password=normalized_password,
            timeout=SSH_LOGIN_TIMEOUT_SECONDS,
            banner_timeout=SSH_LOGIN_TIMEOUT_SECONDS,
            auth_timeout=SSH_LOGIN_TIMEOUT_SECONDS,
            look_for_keys=False,
            allow_agent=False,
        )

        def run(command: str, allowed_exit_codes: Optional[set[int]] = None) -> str:
            stdin, stdout, stderr = client.exec_command(command, timeout=SSH_LOGIN_TIMEOUT_SECONDS)
            del stdin
            output = stdout.read().decode("utf-8", errors="replace")
            error_output = stderr.read().decode("utf-8", errors="replace").strip()
            exit_code = stdout.channel.recv_exit_status()
            if allowed_exit_codes and exit_code in allowed_exit_codes:
                return output
            if exit_code != 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_output or f"{normalized_host}:{port} 硬件信息探测失败",
                )
            return output

        gpu_output = run(
            "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits",
            allowed_exit_codes={0, 127},
        )
        cpu_output = run("nproc")
        memory_output = run(r"free -b | awk '/Mem:/ {print $2}'")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{normalized_host}:{port} 硬件信息探测失败",
        ) from exc
    finally:
        client.close()

    gpu_lines = [line.strip() for line in gpu_output.splitlines() if line.strip()]
    gpu_models: list[str] = []
    gpu_memories_g: list[float] = []
    for line in gpu_lines:
        parts = [item.strip() for item in line.split(",", 1)]
        if len(parts) != 2:
            continue
        gpu_models.append(parts[0])
        gpu_memories_g.append(parse_size_to_g(f"{parts[1]}MB"))

    gpu_count = len(gpu_models)
    gpu_model = gpu_models[0] if gpu_models else "无 GPU"
    if gpu_models and len(set(gpu_models)) > 1:
        gpu_model = " / ".join(sorted(dict.fromkeys(gpu_models)))
    gpu_memory = format_g_value(gpu_memories_g[0] if gpu_memories_g else 0)

    try:
        cpu_cores = max(1, int(cpu_output.strip()))
    except ValueError:
        cpu_cores = 1

    memory_size = format_g_value(parse_size_to_g(f"{memory_output.strip()}B"))

    return {
        "gpu_model": gpu_model,
        "gpu_memory": gpu_memory,
        "gpu_count": gpu_count,
        "cpu_cores": cpu_cores,
        "memory_size": memory_size,
    }


def serialize_user(user: sqlite3.Row) -> dict:
    data = {
        "id": user["id"],
        "username": user["username"],
        "real_name": user["real_name"],
        "role": user["role"],
        "status": user["status"],
    }
    for field_name in (
        "max_ssh_keys_per_user",
        "max_join_keys_per_request",
        "max_containers_per_user",
    ):
        if field_name in user.keys():
            data[field_name] = user[field_name]
    return data


def normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def validate_linux_username(value: str) -> str:
    username = value.strip()
    if not LINUX_USERNAME_PATTERN.fullmatch(username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名只允许小写字母开头，且只能包含小写字母、数字、下划线、短横线，长度不超过 32",
        )
    return username


def compute_ssh_fingerprint(public_key: str) -> str:
    digest = hashlib.sha256(public_key.encode("utf-8")).digest()
    encoded = base64.b64encode(digest).decode("utf-8").rstrip("=")
    return f"SHA256:{encoded}"


def validate_user_role(value: str) -> str:
    role = value.strip()
    if role not in {"admin", "user"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户角色必须是 admin 或 user",
        )
    return role


def validate_user_status(value: str) -> str:
    user_status = value.strip()
    if user_status not in {"active", "disabled"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户状态必须是 active 或 disabled",
        )
    return user_status


def validate_container_status(value: str) -> str:
    container_status = value.strip()
    if container_status not in {"active", "offline", "disabled"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="服务器状态必须是 active、offline 或 disabled",
        )
    return container_status


def clamp_percent(value: float) -> int:
    return max(0, min(100, int(round(float(value)))))


def parse_size_to_g(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return round(float(value), 1)

    normalized = str(value).strip()
    if not normalized:
        return 0.0

    match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*([A-Za-z]*)", normalized)
    if not match:
        return 0.0

    amount = float(match.group(1))
    unit = match.group(2).strip().lower()
    if unit in {"", "g", "gb", "gib"}:
        return round(amount, 1)
    if unit in {"m", "mb", "mib"}:
        return round(amount / 1024.0, 1)
    if unit in {"t", "tb", "tib"}:
        return round(amount * 1024.0, 1)
    if unit in {"k", "kb", "kib"}:
        return round(amount / (1024.0 * 1024.0), 1)
    if unit in {"b", "byte", "bytes"}:
        return round(amount / (1024.0 * 1024.0 * 1024.0), 1)
    return round(amount, 1)


def format_g_value(value: object) -> str:
    numeric = round(float(value or 0), 1)
    if abs(numeric - round(numeric)) < 0.05:
        return f"{int(round(numeric))}G"
    return f"{numeric:.1f}G"


def format_core_value(value: float) -> str:
    numeric = round(float(value), 1)
    if abs(numeric - round(numeric)) < 0.05:
        return str(int(round(numeric)))
    return f"{numeric:.1f}"


def build_gpu_usage_summary(compute_percent: int, used_g: float, total_g: float) -> str:
    return f"{clamp_percent(compute_percent)}% · {format_g_value(used_g)} / {format_g_value(total_g)}"


def build_memory_usage_summary(memory_percent: int, used_g: float, total_g: float) -> str:
    return f"{clamp_percent(memory_percent)}% · {format_g_value(used_g)} / {format_g_value(total_g)}"


def build_cpu_usage_summary(cpu_percent: int, cpu_cores: int) -> str:
    if cpu_cores <= 0:
        return f"{clamp_percent(cpu_percent)}% · -"
    used_cores = cpu_cores * clamp_percent(cpu_percent) / 100.0
    return f"{clamp_percent(cpu_percent)}% · {format_core_value(used_cores)} / {cpu_cores} 核"
