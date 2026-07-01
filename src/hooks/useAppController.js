import { useEffect, useRef, useState } from "react";

import { sendRuntimeHeartbeatRequest } from "../api/client";
import { useAdminController } from "./useAdminController";
import { useAuthController } from "./useAuthController";
import { useWorkspaceController } from "./useWorkspaceController";

const RUNTIME_HEARTBEAT_INTERVAL_MS = 30 * 1000;
const RUNTIME_HEARTBEAT_MIN_GAP_MS = 5 * 1000;
const RUNTIME_VIEW_RELOAD_INTERVAL_MS = 60 * 1000;
const USER_INTERACTION_ACTIVE_WINDOW_MS = 2 * 60 * 1000;

async function copyTextToClipboard(text) {
  const normalizedText = String(text ?? "");

  if (!normalizedText) {
    return false;
  }

  if (window.isSecureContext && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(normalizedText);
    return true;
  }

  const textarea = document.createElement("textarea");
  textarea.value = normalizedText;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.top = "0";
  textarea.style.left = "0";
  textarea.style.opacity = "0";
  textarea.style.pointerEvents = "none";

  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);

  try {
    return document.execCommand("copy");
  } finally {
    document.body.removeChild(textarea);
  }
}

export function useAppController() {
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [activeAccountPanel, setActiveAccountPanel] = useState(null);
  const [confirmDialog, setConfirmDialog] = useState(null);
  const [confirmDialogSubmitting, setConfirmDialogSubmitting] = useState(false);
  const [activeView, setActiveView] = useState("workspace");
  const [sshCopyState, setSshCopyState] = useState(null);
  const accountMenuRef = useRef(null);
  const lastUserInteractionAtRef = useRef(Date.now());
  const runtimeHeartbeatSenderRef = useRef(null);
  const lastRuntimeHeartbeatSentAtRef = useRef(0);

  function resetTransientUiState() {
    setAccountMenuOpen(false);
    setActiveAccountPanel(null);
    setConfirmDialog(null);
    setConfirmDialogSubmitting(false);
    setSshCopyState(null);
  }

  function handleSessionEstablished(user) {
    resetTransientUiState();
    setActiveView(user?.role === "admin" ? "admin" : "workspace");
    workspaceController.setWorkspaceMessage("");
    adminController.setActiveAdminSection("users");
  }

  function handleSessionCleared() {
    resetTransientUiState();
    setActiveView("workspace");
    workspaceController.resetWorkspaceState();
    adminController.resetAdminState();
  }

  const authController = useAuthController({
    onSessionEstablished: handleSessionEstablished,
    onSessionCleared: handleSessionCleared
  });

  function showFloatingTip(message, status = "success", containerId = null) {
    setSshCopyState({
      containerId,
      message,
      status
    });
  }

  const workspaceController = useWorkspaceController({
    session: authController.session,
    activeView,
    csrfToken: authController.csrfToken,
    showFloatingTip,
    setConfirmDialog
  });

  const adminController = useAdminController({
    session: authController.session,
    activeView,
    csrfToken: authController.csrfToken,
    showFloatingTip,
    setConfirmDialog
  });

  useEffect(() => {
    if (!sshCopyState) {
      return;
    }

    const timer = window.setTimeout(() => {
      setSshCopyState(null);
    }, 1800);

    return () => window.clearTimeout(timer);
  }, [sshCopyState]);

  useEffect(() => {
    const hasOpenDialog =
      Boolean(activeAccountPanel) ||
      Boolean(workspaceController.joinDialogContainerId) ||
      Boolean(workspaceController.leaveDialogContainerId) ||
      Boolean(confirmDialog) ||
      adminController.adminUserDialogOpen ||
      adminController.adminContainerDialogOpen;

    if (!hasOpenDialog) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [
    activeAccountPanel,
    workspaceController.joinDialogContainerId,
    workspaceController.leaveDialogContainerId,
    confirmDialog,
    adminController.adminUserDialogOpen,
    adminController.adminContainerDialogOpen
  ]);

  useEffect(() => {
    if (!accountMenuOpen) {
      return;
    }

    function handleOutsidePointerDown(event) {
      if (!accountMenuRef.current?.contains(event.target)) {
        setAccountMenuOpen(false);
      }
    }

    document.addEventListener("pointerdown", handleOutsidePointerDown);
    return () => {
      document.removeEventListener("pointerdown", handleOutsidePointerDown);
    };
  }, [accountMenuOpen]);

  useEffect(() => {
    function markUserInteraction() {
      lastUserInteractionAtRef.current = Date.now();
    }

    const eventOptions = { passive: true };
    window.addEventListener("pointerdown", markUserInteraction, eventOptions);
    window.addEventListener("pointermove", markUserInteraction, eventOptions);
    window.addEventListener("keydown", markUserInteraction);
    window.addEventListener("wheel", markUserInteraction, eventOptions);
    window.addEventListener("touchstart", markUserInteraction, eventOptions);

    return () => {
      window.removeEventListener("pointerdown", markUserInteraction, eventOptions);
      window.removeEventListener("pointermove", markUserInteraction, eventOptions);
      window.removeEventListener("keydown", markUserInteraction);
      window.removeEventListener("wheel", markUserInteraction, eventOptions);
      window.removeEventListener("touchstart", markUserInteraction, eventOptions);
    };
  }, []);

  useEffect(() => {
    const isRuntimeView =
      activeView === "workspace" ||
      (activeView === "admin" && adminController.activeAdminSection === "containers");

    if (!authController.session || !isRuntimeView) {
      runtimeHeartbeatSenderRef.current = null;
      return;
    }

    let heartbeatInFlight = false;

    function reloadRuntimeViewData() {
      if (activeView === "workspace") {
        workspaceController.loadWorkspaceData({ silent: true });
        return;
      }
      if (activeView === "admin" && adminController.activeAdminSection === "containers") {
        adminController.loadAdminData({ silent: true });
      }
    }

    async function sendHeartbeatIfActive() {
      const now = Date.now();
      if (
        heartbeatInFlight ||
        document.visibilityState !== "visible" ||
        now - lastRuntimeHeartbeatSentAtRef.current < RUNTIME_HEARTBEAT_MIN_GAP_MS ||
        now - lastUserInteractionAtRef.current > USER_INTERACTION_ACTIVE_WINDOW_MS
      ) {
        return;
      }

      heartbeatInFlight = true;
      lastRuntimeHeartbeatSentAtRef.current = now;
      try {
        await sendRuntimeHeartbeatRequest();
      } catch {
        // Heartbeat is only a monitor hint; ordinary UI requests handle user-visible errors.
      } finally {
        heartbeatInFlight = false;
      }
    }

    runtimeHeartbeatSenderRef.current = sendHeartbeatIfActive;
    sendHeartbeatIfActive();
    const heartbeatIntervalId = window.setInterval(sendHeartbeatIfActive, RUNTIME_HEARTBEAT_INTERVAL_MS);
    const reloadIntervalId = window.setInterval(() => {
      if (
        document.visibilityState !== "visible" ||
        Date.now() - lastUserInteractionAtRef.current > USER_INTERACTION_ACTIVE_WINDOW_MS
      ) {
        return;
      }
      reloadRuntimeViewData();
    }, RUNTIME_VIEW_RELOAD_INTERVAL_MS);

    return () => {
      runtimeHeartbeatSenderRef.current = null;
      window.clearInterval(heartbeatIntervalId);
      window.clearInterval(reloadIntervalId);
    };
  }, [authController.session, activeView, adminController.activeAdminSection]);

  function updateAuthField(field, value) {
    authController.updateAuthField(field, value);
  }

  function updatePasswordField(field, value) {
    authController.updatePasswordField(field, value);
  }

  function openAccountPanel(panelName) {
    if (authController.session?.role === "admin") {
      setAccountMenuOpen(false);
      return;
    }
    setActiveAccountPanel(panelName);
    setAccountMenuOpen(false);
  }

  async function handleConfirmDialogSubmit() {
    if (!confirmDialog || confirmDialogSubmitting) {
      return;
    }

    const pendingDialog = confirmDialog;
    setConfirmDialogSubmitting(true);

    try {
      if (pendingDialog.type === "ssh-add") {
        await workspaceController.executeAddSshKey(pendingDialog.keyName, pendingDialog.publicKey);
      } else if (pendingDialog.type === "ssh-delete") {
        await workspaceController.executeDeleteSshKey(pendingDialog.sshKeyId);
      } else if (pendingDialog.type === "join") {
        await workspaceController.executeJoinContainer(pendingDialog.containerId, pendingDialog.sshKeyIds);
      } else if (pendingDialog.type === "leave") {
        await workspaceController.executeLeaveContainer(pendingDialog.containerId, pendingDialog.sshKeyIds);
      } else if (pendingDialog.type === "admin-user-create" || pendingDialog.type === "admin-user-update") {
        await adminController.executeAdminUserSubmit(pendingDialog.userId, pendingDialog.payload);
      } else if (pendingDialog.type === "admin-user-delete") {
        await adminController.executeDeleteAdminUser(pendingDialog.userId);
      } else if (pendingDialog.type === "admin-container-create" || pendingDialog.type === "admin-container-update") {
        await adminController.executeAdminContainerSubmit(pendingDialog.containerId, pendingDialog.payload);
      } else if (pendingDialog.type === "admin-container-delete") {
        await adminController.executeDeleteAdminContainer(pendingDialog.containerId);
      }
      setConfirmDialog(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Operation failed";
      workspaceController.setWorkspaceMessage(message);
    } finally {
      setConfirmDialogSubmitting(false);
    }
  }

  async function handleCopySshCommand(containerId, sshCommand) {
    if (!sshCommand) {
      return;
    }

    try {
      const copied = await copyTextToClipboard(sshCommand);

      if (!copied) {
        throw new Error("copy failed");
      }

      showFloatingTip("SSH 命令已复制", "success", containerId);
    } catch {
      showFloatingTip("复制失败，请检查浏览器剪贴板权限", "error", containerId);
    }
  }

  return {
    accountMenuRef,
    accountMenuOpen,
    activeAccountPanel,
    confirmDialog,
    confirmDialogSubmitting,
    activeView,
    sshCopyState,
    setAccountMenuOpen,
    setActiveAccountPanel,
    setConfirmDialog,
    setActiveView,
    updateAuthField,
    updatePasswordField,
    openAccountPanel,
    handleConfirmDialogSubmit,
    handleCopySshCommand,
    ...authController,
    ...workspaceController,
    ...adminController
  };
}
