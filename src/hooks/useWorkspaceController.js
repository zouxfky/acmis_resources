import { useEffect, useRef, useState } from "react";

import {
  addWorkspaceSshKeyRequest,
  deleteWorkspaceSshKeyRequest,
  fetchWorkspaceRequest,
  joinContainerRequest,
  leaveContainerRequest
} from "../api/client";
import { usePollingLeader } from "./usePollingLeader";
import { areIdSetsEqual } from "../utils/formatters";
import {
  decorateWorkspaceContainers,
  formatCooldownLabel,
  getCooldownExpiryTimestamp,
  mapWorkspaceContainers,
  mapWorkspaceSshKeys,
  pruneCooldownEntries,
  readContainerCooldowns,
  writeContainerCooldowns
} from "./workspaceControllerHelpers";


export function useWorkspaceController({
  session,
  activeView,
  csrfToken,
  showFloatingTip,
  setConfirmDialog
}) {
  const workspaceRequestInFlightRef = useRef(false);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [workspaceMessage, setWorkspaceMessage] = useState("");
  const [sshKeys, setSshKeys] = useState([]);
  const [sshKeyNameDraft, setSshKeyNameDraft] = useState("");
  const [sshKeyDraft, setSshKeyDraft] = useState("");
  const [sshStatus, setSshStatus] = useState("idle");
  const [sshMessage, setSshMessage] = useState("");
  const [workspaceContainers, setWorkspaceContainers] = useState([]);
  const [joinDialogContainerId, setJoinDialogContainerId] = useState(null);
  const [joinDialogSelection, setJoinDialogSelection] = useState([]);
  const [joinDialogMessage, setJoinDialogMessage] = useState("");
  const [leaveDialogContainerId, setLeaveDialogContainerId] = useState(null);
  const [leaveDialogSelection, setLeaveDialogSelection] = useState([]);
  const [leaveDialogMessage, setLeaveDialogMessage] = useState("");
  const [containerActionCooldowns, setContainerActionCooldowns] = useState({});
  const [cooldownNow, setCooldownNow] = useState(Date.now());
  const { isPollingLeader: isWorkspacePollingLeader } = usePollingLeader({
    enabled: Boolean(session && activeView === "workspace"),
    scopeKey: `workspace:${session?.id || "guest"}`
  });

  function resetWorkspaceState() {
    setWorkspaceLoading(false);
    setWorkspaceMessage("");
    setSshKeys([]);
    setSshKeyNameDraft("");
    setSshKeyDraft("");
    setSshStatus("idle");
    setSshMessage("");
    setWorkspaceContainers([]);
    setJoinDialogContainerId(null);
    setJoinDialogSelection([]);
    setJoinDialogMessage("");
    setLeaveDialogContainerId(null);
    setLeaveDialogSelection([]);
    setLeaveDialogMessage("");
    setContainerActionCooldowns({});
    setCooldownNow(Date.now());
  }

  function resetWorkspaceDialogs() {
    setJoinDialogContainerId(null);
    setJoinDialogSelection([]);
    setJoinDialogMessage("");
    setLeaveDialogContainerId(null);
    setLeaveDialogSelection([]);
    setLeaveDialogMessage("");
  }

  function applyWorkspaceSshKeys(sshKeyItems) {
    setSshKeys(mapWorkspaceSshKeys(sshKeyItems));
  }

  function replaceWorkspaceContainers(containerItems) {
    setWorkspaceContainers(mapWorkspaceContainers(containerItems));
  }

  function applyWorkspaceData(workspace) {
    applyWorkspaceSshKeys(workspace?.ssh_keys || []);
    replaceWorkspaceContainers(workspace?.containers || []);
  }

  function applyWorkspaceContainerPatch(containerItems) {
    const nextContainers = mapWorkspaceContainers(containerItems);
    if (nextContainers.length === 0) {
      return;
    }

    setWorkspaceContainers((current) => {
      const containerMap = new Map(current.map((item) => [item.id, item]));
      nextContainers.forEach((item) => {
        containerMap.set(item.id, item);
      });
      return current.length === 0
        ? nextContainers
        : current.map((item) => containerMap.get(item.id) || item);
    });
  }

  function getContainerActionCooldownRemainingMs(containerId, now = cooldownNow) {
    const expiresAt = Number(containerActionCooldowns[String(containerId)]) || 0;
    return Math.max(0, expiresAt - now);
  }

  function getContainerActionCooldownLabel(containerId) {
    const remainingMs = getContainerActionCooldownRemainingMs(containerId);
    return remainingMs > 0 ? formatCooldownLabel(remainingMs) : "";
  }

  function startContainerActionCooldown(containerId) {
    const now = Date.now();
    const expiresAt = getCooldownExpiryTimestamp(now);
    setCooldownNow(now);
    setContainerActionCooldowns((current) => ({
      ...pruneCooldownEntries(current),
      [String(containerId)]: expiresAt
    }));
  }

  async function loadWorkspaceData(options = {}) {
    const { silent = false } = options;
    if (workspaceRequestInFlightRef.current) {
      return;
    }

    workspaceRequestInFlightRef.current = true;
    if (!silent) {
      setWorkspaceLoading(true);
    }

    try {
      const data = await fetchWorkspaceRequest();
      applyWorkspaceData(data);
      setWorkspaceMessage("");
    } catch (error) {
      const message = error instanceof Error ? error.message : "工作台数据加载失败";
      setWorkspaceMessage(message);
    } finally {
      workspaceRequestInFlightRef.current = false;
      if (!silent) {
        setWorkspaceLoading(false);
      }
    }
  }

  useEffect(() => {
    if (!session?.id) {
      setContainerActionCooldowns({});
      setCooldownNow(Date.now());
      return;
    }

    setContainerActionCooldowns(readContainerCooldowns(session.id));
    setCooldownNow(Date.now());
  }, [session?.id]);

  useEffect(() => {
    if (!session?.id) {
      return;
    }

    writeContainerCooldowns(session.id, containerActionCooldowns);
  }, [session?.id, containerActionCooldowns]);

  useEffect(() => {
    if (Object.keys(containerActionCooldowns).length === 0) {
      return;
    }

    const intervalId = window.setInterval(() => {
      setCooldownNow(Date.now());
    }, 1000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [containerActionCooldowns]);

  useEffect(() => {
    if (Object.keys(containerActionCooldowns).length === 0) {
      return;
    }

    const nextCooldowns = pruneCooldownEntries(containerActionCooldowns, cooldownNow);
    if (Object.keys(nextCooldowns).length === Object.keys(containerActionCooldowns).length) {
      return;
    }

    setContainerActionCooldowns(nextCooldowns);
  }, [containerActionCooldowns, cooldownNow]);

  useEffect(() => {
    if (!session || activeView !== "workspace") {
      return;
    }

    loadWorkspaceData();

    if (!isWorkspacePollingLeader) {
      return;
    }

    const intervalId = window.setInterval(() => {
      if (document.visibilityState !== "visible") {
        return;
      }
      loadWorkspaceData({ silent: true });
    }, 10000);

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        loadWorkspaceData({ silent: true });
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [session, activeView, isWorkspacePollingLeader]);

  async function handleAddSshKey(event) {
    event.preventDefault();
    const keyName = sshKeyNameDraft.trim();
    const value = sshKeyDraft.trim();

    if (!keyName) {
      setSshStatus("error");
      setSshMessage("请先填写公钥名称");
      return;
    }

    if (!value) {
      setSshStatus("error");
      setSshMessage("请先输入 SSH 公钥");
      return;
    }

    setConfirmDialog({
      type: "ssh-add",
      title: "确认添加 SSH 公钥",
      copy: "确认后会将下列 SSH 公钥加入当前账户",
      keyName,
      publicKey: value,
      keyItems: [
        {
          id: `ssh-add-${Date.now()}`,
          label: keyName,
          value
        }
      ]
    });
  }

  async function executeAddSshKey(keyName, value) {
    setSshStatus("loading");
    setSshMessage("");

    try {
      const data = await addWorkspaceSshKeyRequest(
        {
          key_name: keyName,
          public_key: value
        },
        csrfToken
      );

      applyWorkspaceSshKeys(data.ssh_keys || []);
      setSshKeyNameDraft("");
      setSshKeyDraft("");
      setSshStatus("idle");
      setSshMessage("");
      showFloatingTip("SSH 公钥已添加");
      setWorkspaceMessage("");
    } catch (error) {
      setSshStatus("idle");
      setSshMessage("");
      showFloatingTip(error instanceof Error ? error.message : "SSH 公钥添加失败", "error");
    }
  }

  function handleDeleteSshKey(keyId) {
    const targetKey = sshKeys.find((item) => item.id === keyId);
    if (!targetKey) {
      return;
    }

    setConfirmDialog({
      type: "ssh-delete",
      title: "确认删除 SSH 公钥",
      copy: "确认后会从当前账户移除下列 SSH 公钥",
      sshKeyId: keyId,
      keyItems: [
        {
          id: targetKey.id,
          label: targetKey.label,
          value: targetKey.value
        }
      ]
    });
  }

  async function executeDeleteSshKey(keyId) {
    setSshStatus("loading");
    setSshMessage("");

    try {
      const data = await deleteWorkspaceSshKeyRequest(keyId, csrfToken);
      applyWorkspaceSshKeys(data.ssh_keys || []);
      applyWorkspaceContainerPatch(data.containers || []);
      setSshStatus("idle");
      setSshMessage("");
      showFloatingTip("SSH 公钥已删除");
      setWorkspaceMessage("");
    } catch (error) {
      setSshStatus("idle");
      setSshMessage("");
      showFloatingTip(error instanceof Error ? error.message : "SSH 公钥删除失败", "error");
    }
  }

  function openJoinDialog(containerId) {
    const cooldownLabel = getContainerActionCooldownLabel(containerId);
    if (cooldownLabel) {
      showFloatingTip(`该容器正在冷却中，请在 ${cooldownLabel} 后再操作`, "error");
      return;
    }
    const currentContainer = workspaceContainers.find((item) => item.id === containerId);
    setJoinDialogContainerId(containerId);
    setJoinDialogSelection(currentContainer?.joinedKeyIds || []);
    setJoinDialogMessage("");
  }

  function openLeaveDialog(containerId) {
    const cooldownLabel = getContainerActionCooldownLabel(containerId);
    if (cooldownLabel) {
      showFloatingTip(`该容器正在冷却中，请在 ${cooldownLabel} 后再操作`, "error");
      return;
    }
    const currentContainer = workspaceContainers.find((item) => item.id === containerId);
    setLeaveDialogContainerId(containerId);
    setLeaveDialogSelection(currentContainer?.joinedKeyIds || []);
    setLeaveDialogMessage("");
  }

  function toggleJoinDialogKey(keyId) {
    setJoinDialogSelection((current) => {
      if (current.includes(keyId)) {
        return current.filter((id) => id !== keyId);
      }
      return [...current, keyId];
    });
  }

  async function confirmJoinContainer() {
    if (!joinDialogContainerId) {
      return;
    }

    if (joinDialogSelection.length === 0) {
      setJoinDialogMessage("请至少选择一把 SSH 公钥");
      return;
    }

    const targetContainer = workspaceContainers.find((item) => item.id === joinDialogContainerId);
    const currentJoinedKeyIds = targetContainer?.joinedKeyIds || [];

    if (areIdSetsEqual(joinDialogSelection, currentJoinedKeyIds)) {
      setJoinDialogMessage("当前选择和已加入的 SSH 公钥完全一致");
      return;
    }

    await executeJoinContainer(joinDialogContainerId, [...joinDialogSelection]);
  }

  async function executeJoinContainer(containerId, sshKeyIds) {
    try {
      const data = await joinContainerRequest(containerId, sshKeyIds, csrfToken);

      if (data.container) {
        applyWorkspaceContainerPatch([data.container]);
      }
      startContainerActionCooldown(containerId);
      setJoinDialogContainerId(null);
      setJoinDialogSelection([]);
      setJoinDialogMessage("");
      setWorkspaceMessage("");
      showFloatingTip("加入容器成功");
    } catch (error) {
      setJoinDialogMessage("");
      showFloatingTip(error instanceof Error ? error.message : "容器加入失败", "error");
    }
  }

  function toggleLeaveDialogKey(keyId) {
    setLeaveDialogSelection((current) => {
      if (current.includes(keyId)) {
        return current.filter((id) => id !== keyId);
      }
      return [...current, keyId];
    });
  }

  async function confirmLeaveContainer() {
    if (!leaveDialogContainerId) {
      return;
    }

    const currentContainer = workspaceContainers.find((item) => item.id === leaveDialogContainerId);
    const currentKeys = currentContainer?.joinedKeyIds || [];

    if (currentKeys.length === 0) {
      return;
    }

    if (leaveDialogSelection.length === 0) {
      setLeaveDialogMessage("请至少选择一把要退出的 SSH 公钥");
      return;
    }

    await executeLeaveContainer(leaveDialogContainerId, [...leaveDialogSelection]);
  }

  async function executeLeaveContainer(containerId, sshKeyIds) {
    try {
      const data = await leaveContainerRequest(containerId, sshKeyIds, csrfToken);

      if (data.container) {
        applyWorkspaceContainerPatch([data.container]);
      }
      startContainerActionCooldown(containerId);
      setLeaveDialogContainerId(null);
      setLeaveDialogSelection([]);
      setLeaveDialogMessage("");
      setWorkspaceMessage("");
      showFloatingTip("退出容器成功");
    } catch (error) {
      setLeaveDialogMessage("");
      showFloatingTip(error instanceof Error ? error.message : "容器退出失败", "error");
    }
  }

  const decoratedWorkspaceContainers = decorateWorkspaceContainers(
    workspaceContainers,
    containerActionCooldowns,
    cooldownNow
  );
  const joinedContainers = decoratedWorkspaceContainers.filter((item) => item.joinedKeyIds.length > 0);
  const joinDialogContainer = workspaceContainers.find((item) => item.id === joinDialogContainerId) || null;
  const joinDialogAvailableKeys = joinDialogContainer
    ? sshKeys.filter((item) => !(joinDialogContainer.joinedKeyIds || []).includes(item.id))
    : [];
  const joinDialogSelectionUnchanged = joinDialogContainer
    ? areIdSetsEqual(joinDialogSelection, joinDialogContainer.joinedKeyIds || [])
    : false;
  const leaveDialogContainer = workspaceContainers.find((item) => item.id === leaveDialogContainerId) || null;
  const leaveDialogKeys = leaveDialogContainer
    ? sshKeys.filter((item) => leaveDialogContainer.joinedKeyIds.includes(item.id))
    : [];

  return {
    workspaceLoading,
    workspaceMessage,
    sshKeys,
    sshKeyNameDraft,
    sshKeyDraft,
    sshStatus,
    sshMessage,
    workspaceContainers: decoratedWorkspaceContainers,
    joinDialogContainerId,
    joinDialogSelection,
    joinDialogMessage,
    leaveDialogContainerId,
    leaveDialogSelection,
    leaveDialogMessage,
    joinedContainers,
    joinDialogContainer,
    joinDialogAvailableKeys,
    joinDialogSelectionUnchanged,
    leaveDialogContainer,
    leaveDialogKeys,
    setSshKeyNameDraft,
    setSshKeyDraft,
    setJoinDialogContainerId,
    setLeaveDialogContainerId,
    resetWorkspaceState,
    resetWorkspaceDialogs,
    setWorkspaceMessage,
    handleAddSshKey,
    executeAddSshKey,
    handleDeleteSshKey,
    executeDeleteSshKey,
    openJoinDialog,
    openLeaveDialog,
    toggleJoinDialogKey,
    confirmJoinContainer,
    executeJoinContainer,
    toggleLeaveDialogKey,
    confirmLeaveContainer,
    executeLeaveContainer
  };
}
