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
import {
  buildAdminContainerConfirmItems,
  buildAdminContainerPayload,
  buildAdminUserConfirmItems,
  buildAdminUserPayload,
  hasValidAdminUserQuota,
  isAdminContainerPayloadChanged,
  isAdminUserPayloadChanged
} from "./adminControllerHelpers";

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
      await saveAdminContainerRequest(containerId, payload, csrfToken);
      await loadAdminData();

      setAdminContainersStatus("success");
      setAdminContainersMessage("");
      showFloatingTip(containerId ? "服务器已更新" : "新增服务器成功");
      setAdminContainerForm({ ...emptyAdminContainerForm });
      setSelectedAdminContainerId(null);
      setAdminContainerDialogOpen(false);
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
        setAdminContainerForm({ ...emptyAdminContainerForm });
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
