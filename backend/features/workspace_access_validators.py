from fastapi import HTTPException, status

from backend.core.config import (
    DEFAULT_MAX_CONTAINERS_PER_USER,
    DEFAULT_MAX_JOIN_KEYS_PER_REQUEST,
)


def normalize_ssh_key_ids(ssh_key_ids: list[int]) -> list[int]:
    return sorted({int(item) for item in ssh_key_ids})


def require_non_empty_join_selection(ssh_key_ids: list[int]) -> None:
    if not ssh_key_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少选择一把 SSH 公钥")


def resolve_join_quota_limits(quota_row) -> tuple[int, int]:
    max_join_keys_per_request = (
        int(quota_row["max_join_keys_per_request"]) if quota_row else DEFAULT_MAX_JOIN_KEYS_PER_REQUEST
    )
    max_containers_per_user = (
        int(quota_row["max_containers_per_user"]) if quota_row else DEFAULT_MAX_CONTAINERS_PER_USER
    )
    return max_join_keys_per_request, max_containers_per_user


def validate_join_request_size(ssh_key_ids: list[int], max_join_keys_per_request: int) -> None:
    if len(ssh_key_ids) > max_join_keys_per_request:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"单次最多只能选择 {max_join_keys_per_request} 把 SSH 公钥",
        )


def validate_join_container_row(container_row) -> None:
    if not container_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="容器不存在")
    if container_row["status"] != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前容器不可加入")


def validate_owned_key_ids(selected_key_ids: list[int], owned_key_ids: set[int]) -> None:
    if len(owned_key_ids) != len(selected_key_ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="所选 SSH 公钥不属于当前用户")


def build_inserted_key_ids(selected_key_ids: list[int], existing_selected_ids: set[int]) -> list[int]:
    return [item for item in selected_key_ids if item not in existing_selected_ids]


def validate_user_container_quota(joined_container_count: int, max_containers_per_user: int) -> None:
    if joined_container_count >= max_containers_per_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前账户最多只能加入 {max_containers_per_user} 台容器",
        )


def validate_container_capacity(active_user_count: int, max_users: int) -> None:
    if active_user_count >= max_users:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前容器已达到最大接入人数")


def validate_leave_container_row(container_row) -> None:
    if not container_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="容器不存在")


def validate_current_container_key_ids(current_key_ids: set[int]) -> None:
    if not current_key_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前容器没有可退出的 SSH 公钥绑定")


def resolve_leaving_key_ids(ssh_key_ids: list[int], current_key_ids: set[int]) -> list[int]:
    if ssh_key_ids:
        leaving_key_ids = sorted({int(item) for item in ssh_key_ids})
        if not set(leaving_key_ids).issubset(current_key_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="存在不属于当前容器授权的 SSH 公钥",
            )
        return leaving_key_ids
    return sorted(current_key_ids)


def validate_ssh_key_binding_exists(binding_row) -> None:
    if not binding_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSH 公钥不存在")
