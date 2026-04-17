import { useEffect, useRef, useState } from "react";

import {
  deleteAdminContainerRequest,
  deleteAdminUserRequest,
  fetchAdminContainersRequest,
  fetchAdminUsersRequest,
  saveAdminContainerRequest,
  saveAdminUserRequest
} from "../api/client";
import { emptyAdminContainerForm, emptyAdminUserForm } from "../app/constants";
import { usePollingLeader } from "./usePollingLeader";


export function useAdminController({
  session,
  activeView,
  csrfToken,
  showFloatingTip,
  setConfirmDialog
}) {
  const adminRequestInFlightRef = useRef(false);
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminContainers, setAdminContainers] = useState([]);
  const [adminLoading, setAdminLoading] = useState(false);
  const [adminUsersStatus, setAdminUsersStatus] = useState("idle");
  const [adminUsersMessage, setAdminUsersMessage] = useState("");
  const [adminContainersStatus, setAdminContainersStatus] = useState("idle");
  const [adminContainersMessage, setAdminContainersMessage] = useState("");
  const [adminUserForm, setAdminUserForm] = useState(emptyAdminUserForm);
  const [adminContainerForm, setAdminContainerForm] = useState(emptyAdminContainerForm);
  const [activeAdminSection, setActiveAdminSection] = useState("users");
  const [selectedAdminUserId, setSelectedAdminUserId] = useState(null);
  const [selectedAdminContainerId, setSelectedAdminContainerId] = useState(null);
  const [adminUserDialogOpen, setAdminUserDialogOpen] = useState(false);
  const [adminContainerDialogOpen, setAdminContainerDialogOpen] = useState(false);
  const { isPollingLeader: isAdminPollingLeader } = usePollingLeader({
    enabled: Boolean(session && session.role === "admin" && activeView === "admin"),
    scopeKey: `admin:${session?.id || "guest"}`
  });

  function resetAdminState() {
    setAdminUsers([]);
    setAdminContainers([]);
    setAdminLoading(false);
    setAdminUsersStatus("idle");
    setAdminUsersMessage("");
    setAdminContainersStatus("idle");
    setAdminContainersMessage("");
    setAdminUserForm(emptyAdminUserForm);
    setAdminContainerForm(emptyAdminContainerForm);
    setActiveAdminSection("users");
    setSelectedAdminUserId(null);
    setSelectedAdminContainerId(null);
    setAdminUserDialogOpen(false);
    setAdminContainerDialogOpen(false);
  }

  async function loadAdminData(options = {}) {
    const { silent = false } = options;
    if (adminRequestInFlightRef.current) {
      return;
    }

    adminRequestInFlightRef.current = true;
    if (!silent) {
      setAdminLoading(true);
    }

    try {
      const [usersData, containersData] = await Promise.all([
        fetchAdminUsersRequest(),
        fetchAdminContainersRequest()
      ]);

      setAdminUsers(usersData.items || []);
      setAdminContainers(containersData.items || []);
      setAdminUsersStatus("idle");
      setAdminUsersMessage("");
      setAdminContainersStatus("idle");
      setAdminContainersMessage("");
    } catch (error) {
      const message = error instanceof Error ? error.message : "管理员数据加载失败";
      setAdminUsersStatus("error");
      setAdminUsersMessage(message);
      setAdminContainersStatus("error");
      setAdminContainersMessage(message);
    } finally {
      adminRequestInFlightRef.current = false;
      if (!silent) {
        setAdminLoading(false);
      }
    }
  }

  useEffect(() => {
    if (!session || session.role !== "admin" || activeView !== "admin") {
      return;
    }

    loadAdminData();

    if (!isAdminPollingLeader) {
      return;
    }

    const intervalId = window.setInterval(() => {
      if (document.visibilityState !== "visible") {
        return;
      }
      loadAdminData({ silent: true });
    }, 10000);

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        loadAdminData({ silent: true });
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [session, activeView, isAdminPollingLeader]);

  function updateAdminUserField(field, value) {
    setAdminUserForm((current) => ({
      ...current,
      [field]: value
    }));
  }

  function updateAdminContainerField(field, value) {
    setAdminContainerForm((current) => ({
      ...current,
      [field]: value
    }));
  }

  function startCreateAdminUser() {
    if (adminUserDialogOpen && !adminUserForm.id) {
      cancelAdminUserEdit();
      return;
    }
    setAdminUserForm({ ...emptyAdminUserForm });
    setAdminUsersStatus("idle");
    setAdminUsersMessage("");
    setSelectedAdminUserId(null);
    setAdminUserDialogOpen(true);
  }

  function startEditAdminUser(user) {
    setAdminUserForm({
      id: user.id,
      username: user.username,
      real_name: user.real_name || "",
      password: "",
      role: user.role,
      status: user.status,
      new_password: "",
      max_ssh_keys_per_user: String(user.max_ssh_keys_per_user ?? 12),
      max_join_keys_per_request: String(user.max_join_keys_per_request ?? 5),
      max_containers_per_user: String(user.max_containers_per_user ?? 6)
    });
    setAdminUsersStatus("idle");
    setAdminUsersMessage("");
    setSelectedAdminUserId(user.id);
    setAdminUserDialogOpen(true);
  }

  function cancelAdminUserEdit() {
    setAdminUserForm({ ...emptyAdminUserForm });
    setAdminUsersStatus("idle");
    setAdminUsersMessage("");
    setSelectedAdminUserId(null);
    setAdminUserDialogOpen(false);
  }

  function startCreateAdminContainer() {
    if (adminContainerDialogOpen && !adminContainerForm.id) {
      cancelAdminContainerEdit();
      return;
    }
    setAdminContainerForm({ ...emptyAdminContainerForm });
    setAdminContainersStatus("idle");
    setAdminContainersMessage("");
    setSelectedAdminContainerId(null);
    setAdminContainerDialogOpen(true);
  }

  function startEditAdminContainer(container) {
    setAdminContainerForm({
      id: container.id,
      name: container.name,
      host: container.host,
      ssh_port: String(container.ssh_port),
      root_password: "",
      max_users: String(container.max_users),
      status: container.status
    });
    setAdminContainersStatus("idle");
    setAdminContainersMessage("");
    setSelectedAdminContainerId(container.id);
    setAdminContainerDialogOpen(true);
  }

  function cancelAdminContainerEdit() {
    setAdminContainerForm({ ...emptyAdminContainerForm });
    setAdminContainersStatus("idle");
    setAdminContainersMessage("");
    setSelectedAdminContainerId(null);
    setAdminContainerDialogOpen(false);
  }

  function buildAdminUserPayload() {
    const payload = {
      username: adminUserForm.username.trim(),
      real_name: adminUserForm.real_name.trim() || null,
      role: adminUserForm.role || "user",
      status: adminUserForm.status || "active",
      max_ssh_keys_per_user: Number(adminUserForm.max_ssh_keys_per_user || 12),
      max_join_keys_per_request: Number(adminUserForm.max_join_keys_per_request || 5),
      max_containers_per_user: Number(adminUserForm.max_containers_per_user || 6)
    };

    if (!adminUserForm.id) {
      payload.password = adminUserForm.password.trim();
    } else if (adminUserForm.new_password.trim()) {
      payload.new_password = adminUserForm.new_password.trim();
    }

    if (!adminUserForm.id && !adminUserForm.password.trim()) {
      setAdminUsersStatus("error");
      setAdminUsersMessage("新建用户时必须设置密码");
      return null;
    }

    if (
      !Number.isInteger(payload.max_ssh_keys_per_user) ||
      !Number.isInteger(payload.max_join_keys_per_request) ||
      !Number.isInteger(payload.max_containers_per_user)
    ) {
      setAdminUsersStatus("error");
      setAdminUsersMessage("请填写有效的用户配额");
      return null;
    }

    return payload;
  }

  function isAdminUserPayloadChanged(originalUser, payload) {
    if (!originalUser) {
      return true;
    }

    return (
      payload.username !== (originalUser.username || "") ||
      (payload.real_name || null) !== (originalUser.real_name || null) ||
      payload.role !== (originalUser.role || "user") ||
      payload.status !== (originalUser.status || "active") ||
      payload.max_ssh_keys_per_user !== Number(originalUser.max_ssh_keys_per_user ?? 12) ||
      payload.max_join_keys_per_request !== Number(originalUser.max_join_keys_per_request ?? 5) ||
      payload.max_containers_per_user !== Number(originalUser.max_containers_per_user ?? 6) ||
      Boolean(payload.new_password)
    );
  }

  function handleAdminUserSubmit(event) {
    event?.preventDefault();
    const payload = buildAdminUserPayload();

    if (!payload) {
      return;
    }

    if (adminUserForm.id) {
      const originalUser = adminUsers.find((item) => item.id === adminUserForm.id);

      if (!isAdminUserPayloadChanged(originalUser, payload)) {
        setAdminUsersStatus("idle");
        setAdminUsersMessage("未修改任何内容");
        return;
      }
    }

    setConfirmDialog({
      type: adminUserForm.id ? "admin-user-update" : "admin-user-create",
      title: adminUserForm.id ? `确认更新用户 ${payload.username}` : `确认新增用户 ${payload.username}`,
      copy: adminUserForm.id ? "确认后会保存这名用户的最新信息" : "确认后会创建这名用户账户",
      userId: adminUserForm.id,
      payload,
      keyItems: [
        { id: "username", label: "用户名", value: payload.username },
        { id: "real_name", label: "姓名", value: payload.real_name || "-" },
        { id: "role", label: "角色", value: payload.role },
        { id: "status", label: "状态", value: payload.status },
        {
          id: "password",
          label: "密码",
          value: adminUserForm.id ? (payload.new_password ? "将重置" : "保持不变") : "已设置"
        }
      ]
    });
  }

  async function executeAdminUserSubmit(userId, payload) {
    setAdminUsersStatus("loading");
    setAdminUsersMessage("");

    try {
      await saveAdminUserRequest(userId, payload, csrfToken);
      await loadAdminData();

      setAdminUsersStatus("success");
      setAdminUsersMessage("");
      showFloatingTip(userId ? "用户已更新" : "新增用户成功");
      setAdminUserForm({ ...emptyAdminUserForm });
      setSelectedAdminUserId(null);
      setAdminUserDialogOpen(false);
      await loadAdminData();
    } catch (error) {
      setAdminUsersStatus("error");
      setAdminUsersMessage("");
      showFloatingTip(error instanceof Error ? error.message : "用户保存失败", "error");
    }
  }

  function handleDeleteAdminUser(userItem) {
    setConfirmDialog({
      type: "admin-user-delete",
      title: `确认删除用户 ${userItem.username}`,
      copy: "确认后会删除该用户及其相关授权关系",
      userId: userItem.id,
      keyItems: [
        { id: "username", label: "用户名", value: userItem.username },
        { id: "real_name", label: "姓名", value: userItem.real_name || "-" },
        { id: "role", label: "角色", value: userItem.role },
        { id: "status", label: "状态", value: userItem.status }
      ]
    });
  }

  async function executeDeleteAdminUser(userId) {
    setAdminUsersStatus("loading");
    setAdminUsersMessage("");

    try {
      await deleteAdminUserRequest(userId, csrfToken);
      setAdminUsers((current) => current.filter((item) => item.id !== userId));

      setAdminUsersStatus("success");
      setAdminUsersMessage("");
      showFloatingTip("删除用户成功");
      if (adminUserForm.id === userId) {
        setAdminUserForm({ ...emptyAdminUserForm });
        setAdminUserDialogOpen(false);
      }
      if (selectedAdminUserId === userId) {
        setSelectedAdminUserId(null);
      }
      await loadAdminData();
    } catch (error) {
      setAdminUsersStatus("error");
      setAdminUsersMessage("");
      showFloatingTip(error instanceof Error ? error.message : "用户删除失败", "error");
    }
  }

  function buildAdminContainerPayload() {
    return {
      name: adminContainerForm.name.trim(),
      host: adminContainerForm.host.trim(),
      ssh_port: Number(adminContainerForm.ssh_port || 22),
      root_password: adminContainerForm.root_password.trim() || null,
      max_users: Number(adminContainerForm.max_users || 5),
      status: adminContainerForm.status || "active"
    };
  }

  function isAdminContainerPayloadChanged(originalContainer, payload) {
    if (!originalContainer) {
      return true;
    }

    return (
      payload.name !== (originalContainer.name || "") ||
      payload.host !== (originalContainer.host || "") ||
      payload.ssh_port !== Number(originalContainer.ssh_port ?? 22) ||
      Boolean(payload.root_password) ||
      payload.max_users !== Number(originalContainer.max_users ?? 5) ||
      payload.status !== (originalContainer.status || "active")
    );
  }

  function handleAdminContainerSubmit(event) {
    event?.preventDefault();
    const payload = buildAdminContainerPayload();

    if (adminContainerForm.id) {
      const originalContainer = adminContainers.find((item) => item.id === adminContainerForm.id);

      if (!isAdminContainerPayloadChanged(originalContainer, payload)) {
        setAdminContainersStatus("idle");
        setAdminContainersMessage("未修改任何内容");
        return;
      }
    }

    setConfirmDialog({
      type: adminContainerForm.id ? "admin-container-update" : "admin-container-create",
      title: adminContainerForm.id ? `确认更新服务器 ${payload.name}` : `确认新增服务器 ${payload.name || "未命名服务器"}`,
      copy: adminContainerForm.id ? "确认后会保存这台服务器的最新信息" : "确认后会创建这台服务器记录",
      containerId: adminContainerForm.id,
      payload,
      keyItems: [
        { id: "name", label: "名称", value: payload.name || "-" },
        { id: "host", label: "主机", value: payload.host || "-" },
        { id: "gpu", label: "GPU", value: payload.gpu_model || "-" },
        {
          id: "root_password",
          label: "Root密码",
          value: adminContainerForm.id
            ? (payload.root_password ? "将更新" : "保持不变")
            : (payload.root_password ? "已设置" : "未设置")
        },
        { id: "status", label: "状态", value: payload.status },
        { id: "max_users", label: "最大人数", value: String(payload.max_users) }
      ]
    });
  }

  async function executeAdminContainerSubmit(containerId, payload) {
    setAdminContainersStatus("loading");
    setAdminContainersMessage("");

    try {
      await saveAdminContainerRequest(containerId, payload, csrfToken);
      await loadAdminData();

      setAdminContainersStatus("success");
      setAdminContainersMessage("");
      showFloatingTip(containerId ? "服务器已更新" : "新增服务器成功");
      setAdminContainerForm({ ...emptyAdminContainerForm });
      setSelectedAdminContainerId(null);
      setAdminContainerDialogOpen(false);
      await loadAdminData();
    } catch (error) {
      setAdminContainersStatus("error");
      setAdminContainersMessage("");
      showFloatingTip(error instanceof Error ? error.message : "服务器保存失败", "error");
    }
  }

  function handleDeleteAdminContainer(containerItem) {
    setConfirmDialog({
      type: "admin-container-delete",
      title: `确认删除服务器 ${containerItem.name}`,
      copy: "确认后会删除这台服务器及其相关授权关系",
      containerId: containerItem.id,
      keyItems: [
        { id: "name", label: "名称", value: containerItem.name },
        { id: "host", label: "主机", value: containerItem.host || "-" },
        { id: "status", label: "状态", value: containerItem.status },
        { id: "max_users", label: "最大人数", value: String(containerItem.max_users) }
      ]
    });
  }

  async function executeDeleteAdminContainer(containerId) {
    setAdminContainersStatus("loading");
    setAdminContainersMessage("");

    try {
      await deleteAdminContainerRequest(containerId, csrfToken);
      setAdminContainers((current) => current.filter((item) => item.id !== containerId));

      setAdminContainersStatus("success");
      setAdminContainersMessage("");
      showFloatingTip("删除服务器成功");
      if (adminContainerForm.id === containerId) {
        setAdminContainerForm({ ...emptyAdminContainerForm });
        setAdminContainerDialogOpen(false);
      }
      if (selectedAdminContainerId === containerId) {
        setSelectedAdminContainerId(null);
      }
      await loadAdminData();
    } catch (error) {
      setAdminContainersStatus("error");
      setAdminContainersMessage("");
      showFloatingTip(error instanceof Error ? error.message : "服务器删除失败", "error");
    }
  }

  return {
    adminUsers,
    adminContainers,
    adminLoading,
    adminUsersStatus,
    adminUsersMessage,
    adminContainersStatus,
    adminContainersMessage,
    adminUserForm,
    adminContainerForm,
    activeAdminSection,
    selectedAdminUserId,
    selectedAdminContainerId,
    adminUserDialogOpen,
    adminContainerDialogOpen,
    setActiveAdminSection,
    setAdminUsers,
    setAdminContainers,
    resetAdminState,
    updateAdminUserField,
    updateAdminContainerField,
    startCreateAdminUser,
    startEditAdminUser,
    cancelAdminUserEdit,
    startCreateAdminContainer,
    startEditAdminContainer,
    cancelAdminContainerEdit,
    handleAdminUserSubmit,
    executeAdminUserSubmit,
    handleDeleteAdminUser,
    executeDeleteAdminUser,
    handleAdminContainerSubmit,
    executeAdminContainerSubmit,
    handleDeleteAdminContainer,
    executeDeleteAdminContainer,
    loadAdminData
  };
}
