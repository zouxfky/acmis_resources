import { useEffect, useRef, useState } from "react";

import { useAdminController } from "./useAdminController";
import { useAuthController } from "./useAuthController";
import { useWorkspaceController } from "./useWorkspaceController";

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
  const [activeView, setActiveView] = useState("workspace");
  const [sshCopyState, setSshCopyState] = useState(null);
  const accountMenuRef = useRef(null);

  function resetTransientUiState() {
    setAccountMenuOpen(false);
    setActiveAccountPanel(null);
    setConfirmDialog(null);
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
    if (!confirmDialog) {
      return;
    }

    const pendingDialog = confirmDialog;
    setConfirmDialog(null);

    try {
      if (pendingDialog.type === "ssh-add") {
        await workspaceController.executeAddSshKey(pendingDialog.keyName, pendingDialog.publicKey);
        return;
      }

      if (pendingDialog.type === "ssh-delete") {
        await workspaceController.executeDeleteSshKey(pendingDialog.sshKeyId);
        return;
      }

      if (pendingDialog.type === "join") {
        await workspaceController.executeJoinContainer(pendingDialog.containerId, pendingDialog.sshKeyIds);
        return;
      }

      if (pendingDialog.type === "leave") {
        await workspaceController.executeLeaveContainer(pendingDialog.containerId, pendingDialog.sshKeyIds);
        return;
      }

      if (pendingDialog.type === "admin-user-create" || pendingDialog.type === "admin-user-update") {
        await adminController.executeAdminUserSubmit(pendingDialog.userId, pendingDialog.payload);
        return;
      }

      if (pendingDialog.type === "admin-user-delete") {
        await adminController.executeDeleteAdminUser(pendingDialog.userId);
        return;
      }

      if (pendingDialog.type === "admin-container-create" || pendingDialog.type === "admin-container-update") {
        await adminController.executeAdminContainerSubmit(pendingDialog.containerId, pendingDialog.payload);
        return;
      }

      if (pendingDialog.type === "admin-container-delete") {
        await adminController.executeDeleteAdminContainer(pendingDialog.containerId);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "鎿嶄綔澶辫触";
      workspaceController.setWorkspaceMessage(message);
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

