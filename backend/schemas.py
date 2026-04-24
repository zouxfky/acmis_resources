from typing import Optional

from pydantic import BaseModel, Field

from backend.core.config import (
    DEFAULT_MAX_CONTAINERS_PER_USER,
    DEFAULT_MAX_JOIN_KEYS_PER_REQUEST,
    DEFAULT_MAX_SSH_KEYS_PER_USER,
)


class LoginPayload(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordPayload(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class WorkspaceSshKeyCreatePayload(BaseModel):
    key_name: str = Field(min_length=1, max_length=128)
    public_key: str = Field(min_length=1, max_length=4096)


class WorkspaceContainerBindingPayload(BaseModel):
    ssh_key_ids: list[int] = Field(default_factory=list)


class AdminUserCreatePayload(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    real_name: Optional[str] = Field(default=None, max_length=128)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="user")
    max_ssh_keys_per_user: int = Field(default=DEFAULT_MAX_SSH_KEYS_PER_USER, ge=1, le=100)
    max_join_keys_per_request: int = Field(default=DEFAULT_MAX_JOIN_KEYS_PER_REQUEST, ge=1, le=20)
    max_containers_per_user: int = Field(default=DEFAULT_MAX_CONTAINERS_PER_USER, ge=1, le=50)


class AdminUserUpdatePayload(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    real_name: Optional[str] = Field(default=None, max_length=128)
    role: str = Field(default="user")
    new_password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    max_ssh_keys_per_user: int = Field(default=DEFAULT_MAX_SSH_KEYS_PER_USER, ge=1, le=100)
    max_join_keys_per_request: int = Field(default=DEFAULT_MAX_JOIN_KEYS_PER_REQUEST, ge=1, le=20)
    max_containers_per_user: int = Field(default=DEFAULT_MAX_CONTAINERS_PER_USER, ge=1, le=50)


class AdminContainerPortMappingPayload(BaseModel):
    slot_index: int = Field(ge=1, le=3)
    public_port: Optional[int] = Field(default=None, ge=1, le=65535)
    container_port: Optional[int] = Field(default=None, ge=1, le=65535)


class AdminContainerCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    host: str = Field(min_length=1, max_length=255)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    root_password: Optional[str] = Field(default=None, max_length=255)
    max_users: int = Field(default=3, ge=1, le=999)
    status: str = Field(default="active")
    port_mappings: list[AdminContainerPortMappingPayload] = Field(default_factory=list)


class AdminContainerUpdatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    host: str = Field(min_length=1, max_length=255)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    root_password: Optional[str] = Field(default=None, max_length=255)
    max_users: int = Field(default=3, ge=1, le=999)
    status: str = Field(default="active")
    port_mappings: list[AdminContainerPortMappingPayload] = Field(default_factory=list)
