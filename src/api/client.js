import { formatErrorDetail } from "../utils/formatters";

async function readJson(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(formatErrorDetail(data.detail, "请求失败"));
  }
  return data;
}

function buildJsonHeaders(csrfToken) {
  return {
    "Content-Type": "application/json",
    ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {})
  };
}

function buildHeaders(csrfToken) {
  return csrfToken ? { "X-CSRF-Token": csrfToken } : {};
}

export function fetchSession() {
  return fetch("/api/session", {
    credentials: "include"
  });
}

export async function fetchPublicOverviewRequest() {
  const response = await fetch("/api/public/overview");
  return readJson(response);
}

export async function loginRequest(payload) {
  const response = await fetch("/api/login", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
  return readJson(response);
}

export async function logoutRequest(csrfToken) {
  const response = await fetch("/api/logout", {
    method: "POST",
    credentials: "include",
    headers: buildHeaders(csrfToken)
  });
  return readJson(response);
}

export async function changePasswordRequest(payload, csrfToken) {
  const response = await fetch("/api/change-password", {
    method: "POST",
    credentials: "include",
    headers: buildJsonHeaders(csrfToken),
    body: JSON.stringify(payload)
  });
  return readJson(response);
}

export async function fetchWorkspaceRequest() {
  const response = await fetch("/api/workspace", { credentials: "include" });
  return readJson(response);
}

export async function addWorkspaceSshKeyRequest(payload, csrfToken) {
  const response = await fetch("/api/workspace/ssh-keys", {
    method: "POST",
    credentials: "include",
    headers: buildJsonHeaders(csrfToken),
    body: JSON.stringify(payload)
  });
  return readJson(response);
}

export async function deleteWorkspaceSshKeyRequest(sshKeyId, csrfToken) {
  const response = await fetch(`/api/workspace/ssh-keys/${sshKeyId}`, {
    method: "DELETE",
    credentials: "include",
    headers: buildHeaders(csrfToken)
  });
  return readJson(response);
}

export async function joinContainerRequest(containerId, sshKeyIds, csrfToken) {
  const response = await fetch(`/api/workspace/containers/${containerId}/join`, {
    method: "POST",
    credentials: "include",
    headers: buildJsonHeaders(csrfToken),
    body: JSON.stringify({ ssh_key_ids: sshKeyIds })
  });
  return readJson(response);
}

export async function leaveContainerRequest(containerId, sshKeyIds, csrfToken) {
  const response = await fetch(`/api/workspace/containers/${containerId}/leave`, {
    method: "POST",
    credentials: "include",
    headers: buildJsonHeaders(csrfToken),
    body: JSON.stringify({ ssh_key_ids: sshKeyIds })
  });
  return readJson(response);
}

export async function fetchAdminUsersRequest() {
  const response = await fetch("/api/admin/users", { credentials: "include" });
  return readJson(response);
}

export async function fetchAdminContainersRequest() {
  const response = await fetch("/api/admin/containers", { credentials: "include" });
  return readJson(response);
}

export async function saveAdminUserRequest(userId, payload, csrfToken) {
  const response = await fetch(userId ? `/api/admin/users/${userId}` : "/api/admin/users", {
    method: userId ? "PUT" : "POST",
    credentials: "include",
    headers: buildJsonHeaders(csrfToken),
    body: JSON.stringify(payload)
  });
  return readJson(response);
}

export async function deleteAdminUserRequest(userId, csrfToken) {
  const response = await fetch(`/api/admin/users/${userId}`, {
    method: "DELETE",
    credentials: "include",
    headers: buildHeaders(csrfToken)
  });
  return readJson(response);
}

export async function saveAdminContainerRequest(containerId, payload, csrfToken) {
  const response = await fetch(
    containerId ? `/api/admin/containers/${containerId}` : "/api/admin/containers",
    {
      method: containerId ? "PUT" : "POST",
      credentials: "include",
      headers: buildJsonHeaders(csrfToken),
      body: JSON.stringify(payload)
    }
  );
  return readJson(response);
}

export async function deleteAdminContainerRequest(containerId, csrfToken) {
  const response = await fetch(`/api/admin/containers/${containerId}`, {
    method: "DELETE",
    credentials: "include",
    headers: buildHeaders(csrfToken)
  });
  return readJson(response);
}
