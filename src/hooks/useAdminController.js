import { useEffect, useRef, useState } from "react";

import {
  deleteAdminContainerRequest,
  deleteAdminUserRequest,
  fetchAdminContainersRequest,
  fetchAdminUsersRequest,
  saveAdminContainerRequest,
  saveAdminUserRequest,
  syncAllAdminContainersRequest
} from "../api/client";
import { createEmptyAdminContainerForm, emptyAdminUserForm } from "../app/constants";
import {
  buildAdminContainerConfirmItems,
  buildAdminContainerPayload,
  buildAdminUserConfirmItems,
  buildAdminUserPayload,
  hasValidAdminUserQuota,
  isAdminContainerPayloadChanged,
  isAdminUserPayloadChanged
} from "./adminControllerHelpers";

const SYNC_ALL_CONTAINERS_COOLDOWN_SECONDS = 3 * 60;

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
  const [adminContainerForm, setAdminContainerForm] = useState(createEmptyAdminContainerForm());
  const [activeAdminSection, setActiveAdminSection] = useState("users");
  const [selectedAdminUserId, setSelectedAdminUserId] = useState(null);
  const [selectedAdminContainerId, setSelectedAdminContainerId] = useState(null);
  const [adminUserDialogOpen, setAdminUserDialogOpen] = useState(false);
  const [adminContainerDialogOpen, setAdminContainerDialogOpen] = useState(false);
  const [syncAllContainersStatus, setSyncAllContainersStatus] = useState("idle");
  const [syncAllContainersCooldownUntil, setSyncAllContainersCooldownUntil] = useState(0);
  const [syncAllContainersNow, setSyncAllContainersNow] = useState(Date.now());
  function resetAdminState() {
    setAdminUsers([]);
    setAdminContainers([]);
    setAdminLoading(false);
    setAdminUsersStatus("idle");
    setAdminUsersMessage("");
    setAdminContainersStatus("idle");
    setAdminContainersMessage("");
    setAdminUserForm(emptyAdminUserForm);
    setAdminContainerForm(createEmptyAdminContainerForm());
    setActiveAdminSection("users");
    setSelectedAdminUserId(null);
    setSelectedAdminContainerId(null);
    setAdminUserDialogOpen(false);
    setAdminContainerDialogOpen(false);
    setSyncAllContainersStatus("idle");
    setSyncAllContainersCooldownUntil(0);
    setSyncAllContainersNow(Date.now());
  }

  const syncAllContainersCooldownRemainingSeconds = Math.max(
    0,
    Math.ceil((syncAllContainersCooldownUntil - syncAllContainersNow) / 1000)
  );

  useEffect(() => {
    if (syncAllContainersCooldownRemainingSeconds <= 0) {
      return;
    }

    const intervalId = window.setInterval(() => {
      setSyncAllContainersNow(Date.now());
    }, 1000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [syncAllContainersCooldownRemainingSeconds]);

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

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        loadAdminData({ silent: true });
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [session, activeView]);

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

  function updateAdminContainerPortMapping(slotIndex, field, value) {
    setAdminContainerForm((current) => ({
      ...current,
      port_mappings: (current.port_mappings || []).map((item) =>
        Number(item.slot_index) === Number(slotIndex)
          ? {
              ...item,
              [field]: value
            }
          : item
      )
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
      new_password: "",
      max_ssh_keys_per_user: String(user.max_ssh_keys_per_user ?? 5),
      max_join_keys_per_request: String(user.max_join_keys_per_request ?? 5),
      max_containers_per_user: String(user.max_containers_per_user ?? 4)
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
    setAdminContainerForm(createEmptyAdminContainerForm());
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
      status: container.status,
      port_mappings: Array.from({ length: 3 }, (_, index) => {
        const slotIndex = index + 1;
        const existingMapping = Array.isArray(container.port_mappings)
          ? container.port_mappings.find((item) => Number(item.slot_index) === slotIndex)
          : null;
        return {
          slot_index: slotIndex,
          public_port: existingMapping ? String(existingMapping.public_port) : "",
          container_port: existingMapping ? String(existingMapping.container_port) : ""
        };
      })
    });
    setAdminContainersStatus("idle");
    setAdminContainersMessage("");
    setSelectedAdminContainerId(container.id);
    setAdminContainerDialogOpen(true);
  }

  function cancelAdminContainerEdit() {
    setAdminContainerForm(createEmptyAdminContainerForm());
    setAdminContainersStatus("idle");
    setAdminContainersMessage("");
    setSelectedAdminContainerId(null);
    setAdminContainerDialogOpen(false);
  }

  function getAdminUserPayload() {
    const payload = buildAdminUserPayload(adminUserForm);
    if (!adminUserForm.id && !adminUserForm.password.trim()) {
      setAdminUsersStatus("error");
      setAdminUsersMessage("新建用户时必须设置密码");
      return null;
    }

    if (!hasValidAdminUserQuota(payload)) {
      setAdminUsersStatus("error");
      setAdminUsersMessage("请填写有效的用户配额");
      return null;
    }

    return payload;
  }

  function handleAdminUserSubmit(event) {
    event?.preventDefault();
    const payload = getAdminUserPayload();

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
      keyItems: buildAdminUserConfirmItems(adminUserForm, payload)
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
        { id: "role", label: "角色", value: userItem.role }
      ]
    });
  }

  async function executeDeleteAdminUser(userId) {
    setAdminUsersStatus("loading");
    setAdminUsersMessage("");

    try {
      const data = await deleteAdminUserRequest(userId, csrfToken);
      setAdminUsers((current) => current.filter((item) => item.id !== userId));

      setAdminUsersStatus("success");
      setAdminUsersMessage("");
      showFloatingTip(data?.message || "User deleted");
      if (adminUserForm.id === userId) {
        setAdminUserForm({ ...emptyAdminUserForm });
        setAdminUserDialogOpen(false);
      }
      if (selectedAdminUserId === userId) {
        setSelectedAdminUserId(null);
      }
    } catch (error) {
      setAdminUsersStatus("error");
      setAdminUsersMessage("");
      showFloatingTip(error instanceof Error ? error.message : "用户删除失败", "error");
    }
  }

  function handleAdminContainerSubmit(event) {
    event?.preventDefault();
    const payload = buildAdminContainerPayload(adminContainerForm);

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
      keyItems: buildAdminContainerConfirmItems(adminContainerForm, payload)
    });
  }

  async function executeAdminContainerSubmit(containerId, payload) {
    setAdminContainersStatus("loading");
    setAdminContainersMessage("");

    try {
      const data = await saveAdminContainerRequest(containerId, payload, csrfToken);
      await loadAdminData();

      setAdminContainersStatus("success");
      setAdminContainersMessage("");
      showFloatingTip(data?.message || (containerId ? "Server updated" : "Server created"));
      setAdminContainerForm(createEmptyAdminContainerForm());
      setSelectedAdminContainerId(null);
      setAdminContainerDialogOpen(false);
    } catch (error) {
      setAdminContainersStatus("error");
      setAdminContainersMessage("");
      showFloatingTip(error instanceof Error ? error.message : "服务器保存失败", "error");
    }
  }

  async function syncAllAdminContainers() {
    if (syncAllContainersStatus === "loading" || syncAllContainersCooldownRemainingSeconds > 0) {
      return;
    }

    setSyncAllContainersStatus("loading");
    setSyncAllContainersNow(Date.now());
    setSyncAllContainersCooldownUntil(Date.now() + SYNC_ALL_CONTAINERS_COOLDOWN_SECONDS * 1000);

    try {
      const data = await syncAllAdminContainersRequest(csrfToken);
      await loadAdminData({ silent: true });
      setSyncAllContainersStatus("idle");
      showFloatingTip(data?.message || "同步刷新完成");
    } catch (error) {
      setSyncAllContainersStatus("idle");
      setSyncAllContainersCooldownUntil(0);
      setSyncAllContainersNow(Date.now());
      showFloatingTip(error instanceof Error ? error.message : "同步刷新失败", "error");
    }
  }

  function handleDeleteAdminContainer(containerItem) {
    setConfirmDialog({
      type: "admin-container-delete",
      title: `确认删除服务器 ${containerItem.name}`,
      copy: "确认后会先清理这台服务器内的 SSH 授权，再删除服务器记录",
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
        setAdminContainerForm(createEmptyAdminContainerForm());
        setAdminContainerDialogOpen(false);
      }
      if (selectedAdminContainerId === containerId) {
        setSelectedAdminContainerId(null);
      }
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
    syncAllContainersStatus,
    syncAllContainersCooldownRemainingSeconds,
    setActiveAdminSection,
    setAdminUsers,
    setAdminContainers,
    resetAdminState,
    updateAdminUserField,
    updateAdminContainerField,
    updateAdminContainerPortMapping,
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
    syncAllAdminContainers,
    handleDeleteAdminContainer,
    executeDeleteAdminContainer,
    loadAdminData
  };
}
