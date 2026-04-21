export function buildAdminUserPayload(form) {
  const payload = {
    username: form.username.trim(),
    real_name: form.real_name.trim() || null,
    role: form.role || "user",
    max_ssh_keys_per_user: Number(form.max_ssh_keys_per_user || 5),
    max_join_keys_per_request: Number(form.max_join_keys_per_request || 5),
    max_containers_per_user: Number(form.max_containers_per_user || 4)
  };

  if (!form.id) {
    payload.password = form.password.trim();
  } else if (form.new_password.trim()) {
    payload.new_password = form.new_password.trim();
  }

  return payload;
}

export function hasValidAdminUserQuota(payload) {
  return (
    Number.isInteger(payload.max_ssh_keys_per_user) &&
    Number.isInteger(payload.max_join_keys_per_request) &&
    Number.isInteger(payload.max_containers_per_user)
  );
}

export function isAdminUserPayloadChanged(originalUser, payload) {
  if (!originalUser) {
    return true;
  }

  return (
    payload.username !== (originalUser.username || "") ||
    (payload.real_name || null) !== (originalUser.real_name || null) ||
    payload.role !== (originalUser.role || "user") ||
    payload.max_ssh_keys_per_user !== Number(originalUser.max_ssh_keys_per_user ?? 5) ||
    payload.max_join_keys_per_request !== Number(originalUser.max_join_keys_per_request ?? 5) ||
    payload.max_containers_per_user !== Number(originalUser.max_containers_per_user ?? 4) ||
    Boolean(payload.new_password)
  );
}

export function buildAdminUserConfirmItems(form, payload) {
  return [
    { id: "username", label: "用户名", value: payload.username },
    { id: "real_name", label: "姓名", value: payload.real_name || "-" },
    { id: "role", label: "角色", value: payload.role },
    {
      id: "password",
      label: "密码",
      value: form.id ? (payload.new_password ? "将重置" : "保持不变") : "已设置"
    }
  ];
}

export function buildAdminContainerPayload(form) {
  return {
    name: form.name.trim(),
    host: form.host.trim(),
    ssh_port: Number(form.ssh_port || 22),
    root_password: form.root_password.trim() || null,
    max_users: Number(form.max_users || 3),
    status: form.status || "active"
  };
}

export function isAdminContainerPayloadChanged(originalContainer, payload) {
  if (!originalContainer) {
    return true;
  }

  return (
    payload.name !== (originalContainer.name || "") ||
    payload.host !== (originalContainer.host || "") ||
    payload.ssh_port !== Number(originalContainer.ssh_port ?? 22) ||
    Boolean(payload.root_password) ||
    payload.max_users !== Number(originalContainer.max_users ?? 3) ||
    payload.status !== (originalContainer.status || "active")
  );
}

export function buildAdminContainerConfirmItems(form, payload) {
  return [
    { id: "name", label: "名称", value: payload.name || "-" },
    { id: "host", label: "主机", value: payload.host || "-" },
    {
      id: "root_password",
      label: "Root密码",
      value: form.id
        ? (payload.root_password ? "将更新" : "保持不变")
        : (payload.root_password ? "已设置" : "未设置")
    },
    { id: "status", label: "状态", value: payload.status },
    { id: "max_users", label: "最大人数", value: String(payload.max_users) }
  ];
}
