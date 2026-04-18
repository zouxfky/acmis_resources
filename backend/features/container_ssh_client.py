from fastapi import HTTPException, status

from backend.core.config import SSH_CONNECT_TIMEOUT_SECONDS, SSH_SYNC_COMMAND_TIMEOUT_SECONDS

try:
    import paramiko
except ImportError:  # pragma: no cover - depends on local environment
    paramiko = None


class ContainerSSHConnectError(RuntimeError):
    pass


class ContainerSSHSyncError(RuntimeError):
    pass


def exec_ssh_command(client: "paramiko.SSHClient", command: str) -> str:
    stdin, stdout, stderr = client.exec_command(command, timeout=SSH_SYNC_COMMAND_TIMEOUT_SECONDS)
    del stdin
    output = stdout.read().decode("utf-8", errors="replace")
    error_output = stderr.read().decode("utf-8", errors="replace").strip()
    exit_code = stdout.channel.recv_exit_status()
    if exit_code != 0:
        raise ContainerSSHSyncError(error_output or "远端 SSH 授权同步命令执行失败")
    return output


def open_root_client(host: str, ssh_port: int, root_password: str) -> "paramiko.SSHClient":
    if paramiko is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="后端未安装 paramiko，无法同步容器 SSH 授权",
        )

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
    except Exception as exc:
        client.close()
        raise ContainerSSHConnectError(f"{host}:{ssh_port}") from exc
    return client
